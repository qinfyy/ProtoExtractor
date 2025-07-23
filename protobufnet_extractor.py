import re
from collections import defaultdict

TYPE_MAPPING = {
    'int': 'int32',
    'long': 'int64',
    'float': 'float',
    'double': 'double',
    'bool': 'bool',
    'string': 'string',
    'uint': 'uint32',
    'ulong': 'uint64',
}

def apply_data_format(proto_type, data_format):
    if not data_format:
        return proto_type

    data_format = data_format.lower()

    if 'zigzag' in data_format:
        if proto_type in ['int32', 'int']:
            return 'sint32'
        elif proto_type in ['int64', 'long']:
            return 'sint64'
    elif 'fixed' in data_format or 'fixedsize' in data_format:
        if proto_type in ['int32', 'int']:
            return 'sfixed32'
        elif proto_type in ['int64', 'long']:
            return 'sfixed64'
        elif proto_type in ['uint32', 'uint']:
            return 'fixed32'
        elif proto_type in ['uint64', 'ulong']:
            return 'fixed64'

    return proto_type

def get_proto_type(csharp_type, data_format=None, key_format=None, value_format=None):
    if 'byte[]' == csharp_type.strip():
        return 'bytes', False

    csharp_type = csharp_type.replace('?', '').strip()
    original_type = csharp_type

    is_repeated = False
    key_type = None
    value_type = None

    if 'Dictionary<' in csharp_type or 'global::System.Collections.Generic.Dictionary<' in csharp_type:
        match = re.search(r'Dictionary\s*<\s*([\w\s,\[\]<>\.:]+)\s*,\s*([\w\s,\[\]<>\.:]+)\s*>', csharp_type)
        if match:
            key_type = match.group(1).strip()
            value_type = match.group(2).strip()

            proto_key_type, _ = get_proto_type(key_type, data_format=key_format)
            proto_value_type, _ = get_proto_type(value_type, data_format=value_format)

            if '.' in proto_value_type:
                proto_value_type = proto_value_type.split('.')[-1]

            return f'map<{proto_key_type}, {proto_value_type}>', False

    if csharp_type.startswith('List<') or csharp_type.startswith('global::System.Collections.Generic.List<'):
        is_repeated = True
        match = re.search(r'List<([\w\s,\[\]<>\.:]+)>', csharp_type)
        if match:
            csharp_type = match.group(1).strip()
        else:
            csharp_type = csharp_type[5:-1].strip()
    elif csharp_type.endswith('[]'):
        is_repeated = True
        csharp_type = csharp_type[:-2].strip()
    elif '[]' in csharp_type:
        is_repeated = True
        csharp_type = csharp_type.replace('[]', '').strip()

    if csharp_type == 'byte[]' or 'List<byte[]' in original_type:
        return 'bytes', True

    proto_type = TYPE_MAPPING.get(csharp_type, csharp_type)

    if '.' in proto_type:
        proto_type = proto_type.split('.')[-1]

    if data_format:
        proto_type = apply_data_format(proto_type, data_format)

    return proto_type, is_repeated

def find_matching_brace(content, start_index=0):
    stack = []
    in_single_comment = False
    in_multi_comment = False
    in_string = False
    in_char = False
    escape = False

    i = start_index
    n = len(content)

    while i < n:
        char = content[i]
        next_char = content[i+1] if i+1 < n else None

        if escape:
            escape = False
            i += 1
            continue

        if char == '\\':
            escape = True
            i += 1
            continue

        if not in_string and not in_char:
            if in_single_comment:
                if char == '\n':
                    in_single_comment = False
            elif in_multi_comment:
                if char == '*' and next_char == '/':
                    in_multi_comment = False
                    i += 1
            else:
                if char == '/' and next_char == '/':
                    in_single_comment = True
                    i += 1
                elif char == '/' and next_char == '*':
                    in_multi_comment = True
                    i += 1

        if not in_single_comment and not in_multi_comment:
            if char == '"' and not in_char:
                in_string = not in_string
            elif char == "'" and not in_string:
                in_char = not in_char

        if not in_single_comment and not in_multi_comment and not in_string and not in_char:
            if char == '{':
                stack.append(i)
            elif char == '}':
                if stack:
                    stack.pop()
                    if not stack:
                        return i + 1

        i += 1

    return -1

def extract_class_definitions(content):
    classes = []

    class_pattern = re.compile(
        r'\[\s*global::ProtoBuf\.ProtoContract\s*[^\]]*\]\s*'
        r'public\s+partial\s+class\s+(\w+)\s*:\s*[^{]+\{',
        re.DOTALL
    )

    start_pos = 0
    while start_pos < len(content):
        class_match = class_pattern.search(content, start_pos)
        if not class_match:
            break

        class_name = class_match.group(1)
        class_start = class_match.end()
        class_end = find_matching_brace(content, class_match.start())

        if class_end > class_start:
            class_body = content[class_start:class_end]
            classes.append((class_name, class_body))
            nested_start = 0
            while nested_start < len(class_body):
                nested_match = class_pattern.search(class_body, nested_start)
                if not nested_match:
                    break

                nested_name = nested_match.group(1)
                nested_class_start = nested_match.end()
                nested_class_end = find_matching_brace(class_body, nested_match.start())

                if nested_class_end > nested_class_start:
                    nested_body = class_body[nested_class_start:nested_class_end]
                    classes.append((f"{class_name}.{nested_name}", nested_body))
                    nested_start = nested_class_end
                else:
                    nested_start = nested_match.end()
            start_pos = class_end
        else:
            start_pos = class_match.end()

    return classes

def extract_enums_from_content(content, parent_class=None, exclude_regions=None):
    enum_block_pattern = re.compile(
        r'\[\s*global::ProtoBuf\.ProtoContract[^\]]*\]\s*'
        r'public\s+enum\s+(\w+)\s*\{([^}]+)\}',
        re.DOTALL
    )

    item_pattern = re.compile(
        r'\[\s*global::ProtoBuf\.ProtoEnum[^\]]*Name\s*=\s*@?"([^"]+)"[^\]]*\]\s*'
        r'(\w+)\s*=\s*(\d+)'
    )

    plain_enum_pattern = re.compile(r'(\w+)\s*=\s*(\d+)\b')

    enums = []
    processed_enums = set()

    for enum_match in enum_block_pattern.finditer(content):
        if exclude_regions:
            match_start = enum_match.start()
            match_end = enum_match.end()
            excluded = False
            for (start, end) in exclude_regions:
                if start <= match_start < end or start <= match_end < end:
                    excluded = True
                    break
            if excluded:
                continue

        enum_name = enum_match.group(1)

        if enum_name in processed_enums:
            continue
        processed_enums.add(enum_name)

        enum_body = enum_match.group(2)
        enum_items = []
        used_values = set()

        for item_match in item_pattern.finditer(enum_body):
            proto_name = item_match.group(1)
            csharp_name = item_match.group(2)
            value = int(item_match.group(3))
            used_values.add(value)
            enum_items.append((proto_name, value))

        for plain_match in plain_enum_pattern.finditer(enum_body):
            csharp_name = plain_match.group(1)
            value = int(plain_match.group(2))
            if value in used_values:
                continue
            enum_items.append((csharp_name, value))

        enum_items.sort(key=lambda x: x[1])
        enums.append({
            'name': enum_name,
            'items': enum_items,
            'parent_class': parent_class
        })

    return enums

def extract_fields_from_class(class_body):
    field_pattern = re.compile(
        r'\[\s*global::ProtoBuf\.ProtoMember\s*\(([^)]+)\)\s*\][\s\S]*?'
        r'public\s+(?:readonly\s+|const\s+)?([\w<>,\[\]\s\.:]+?)\s+(\w+)\s*(?:\{|;)',
        re.DOTALL
    )

    default_value_pattern = re.compile(
        r'DefaultValue\s*\(\s*([^)]+)\s*\)\]\s*|=\s*([^;\n{]+)\s*(?:;|\{)',
        re.DOTALL
    )

    oneof_group_pattern = re.compile(
        r'private\s+global::ProtoBuf\.DiscriminatedUnion(?:\d+)?(?:Object)?\s+(\w+);',
        re.DOTALL
    )

    oneof_field_pattern = re.compile(
        r'\[\s*global::ProtoBuf\.ProtoMember\s*\(([^)]+)\)\s*\][\s\S]*?'
        r'public\s+([\w<>,\[\]\s\.:]+?)\s+(\w+)\s*\{'
        r'([\s\S]*?)\}',
        re.DOTALL
    )

    proto_map_pattern = re.compile(
        r'\[\s*global::ProtoBuf\.ProtoMap\s*\(([^)]*)\)\s*\]',
        re.DOTALL
    )

    def parse_proto_member_args(args_str):
        tag_match = re.search(r'(\d+)', args_str)
        tag = int(tag_match.group(1)) if tag_match else None

        data_format_match = re.search(r'DataFormat\s*=\s*global::ProtoBuf\.DataFormat\.(\w+)', args_str)
        data_format = data_format_match.group(1) if data_format_match else None

        is_packed = re.search(r'IsPacked\s*=\s*true', args_str) is not None

        name_match = re.search(r'Name\s*=\s*@?"([^"]+)"', args_str)
        name = name_match.group(1) if name_match else None

        return tag, data_format, is_packed, name

    def parse_proto_map_args(args_str):
        key_format = None
        value_format = None

        key_match = re.search(r'KeyFormat\s*=\s*global::ProtoBuf\.DataFormat\.(\w+)', args_str)
        if key_match:
            key_format = key_match.group(1)

        value_match = re.search(r'ValueFormat\s*=\s*global::ProtoBuf\.DataFormat\.(\w+)', args_str)
        if value_match:
            value_format = value_match.group(1)

        return key_format, value_format

    fields = []
    oneof_groups = defaultdict(list)
    oneof_original_field_names = set()

    nested_class_regions = []
    nested_pattern = re.compile(r'public\s+partial\s+class\s+\w+\s*:\s*[^{]+\{', re.DOTALL)
    pos = 0
    while pos < len(class_body):
        match = nested_pattern.search(class_body, pos)
        if not match:
            break
        start_index = match.start()
        end_index = find_matching_brace(class_body, start_index)
        if end_index > start_index:
            nested_class_regions.append((start_index, end_index))
            pos = end_index
        else:
            pos = match.end()

    def in_nested_region(index):
        for (start, end) in nested_class_regions:
            if start <= index < end:
                return True
        return False

    for oneof_group_match in oneof_group_pattern.finditer(class_body):
        if in_nested_region(oneof_group_match.start()):
            continue

        field_name = oneof_group_match.group(1)
        oneof_group_name = re.sub(r'^__pbn__', '', field_name)
        oneof_groups[oneof_group_name] = []

    for oneof_field_match in oneof_field_pattern.finditer(class_body):
        if in_nested_region(oneof_field_match.start()):
            continue

        args_str = oneof_field_match.group(1)
        csharp_type = oneof_field_match.group(2).strip()
        original_field_name = oneof_field_match.group(3)
        method_body = oneof_field_match.group(4)

        if '__pbn__' not in method_body:
            continue

        tag, data_format, is_packed, name_override = parse_proto_member_args(args_str)
        if not tag:
            continue

        union_matches = re.findall(r'__pbn__(\w+)\b', method_body)
        if not union_matches:
            continue

        union_base_name = re.sub(r'^__pbn__', '', union_matches[0])

        proto_type, _ = get_proto_type(csharp_type, data_format)
        default_value = None

        default_match = default_value_pattern.search(method_body)
        if default_match:
            if default_match.group(1):
                default_value = default_match.group(1).strip(' "\'')
            elif default_match.group(2):
                default_value = default_match.group(2).strip(' "\'')

        if default_value and any(x in default_value for x in ['__pbn__', '?', ':', '>', '<', 'default']):
            default_value = None

        field_name = name_override if name_override else original_field_name
        oneof_original_field_names.add(original_field_name)

        for possible_name in [union_base_name, re.sub(r'\d+$', '', union_base_name)]:
            if possible_name in oneof_groups:
                oneof_groups[possible_name].append({
                    'tag': tag,
                    'name': field_name,
                    'type': proto_type,
                    'default': default_value
                })
                break
        else:
            if oneof_groups:
                first_group = next(iter(oneof_groups.keys()))
                oneof_groups[first_group].append({
                    'tag': tag,
                    'name': field_name,
                    'type': proto_type,
                    'default': default_value
                })

    for field_match in field_pattern.finditer(class_body):
        if in_nested_region(field_match.start()):
            continue

        field_text = field_match.group(0)
        args_str = field_match.group(1)
        csharp_type = field_match.group(2).strip()
        original_field_name = field_match.group(3)

        if original_field_name in oneof_original_field_names:
            continue

        tag, data_format, is_packed, name_override = parse_proto_member_args(args_str)
        if not tag:
            continue

        field_name = name_override if name_override else original_field_name

        key_format = None
        value_format = None
        map_match = proto_map_pattern.search(field_text)
        if map_match:
            map_args = map_match.group(1)
            key_format, value_format = parse_proto_map_args(map_args)

        proto_type, is_repeated = get_proto_type(
            csharp_type,
            data_format=data_format,
            key_format=key_format,
            value_format=value_format
        )

        is_repeated = is_repeated or (is_packed and proto_type in ['int32', 'int64', 'uint32', 'uint64',
                                                                   'sint32', 'sint64', 'fixed32', 'fixed64',
                                                                   'sfixed32', 'sfixed64', 'float', 'double'])

        default_value = None
        default_match = default_value_pattern.search(field_text)
        if default_match:
            if default_match.group(1):
                default_value = default_match.group(1).strip(' "\'')
            elif default_match.group(2):
                default_value = default_match.group(2).strip(' "\'')

        if default_value and (default_value.startswith('new ') or any(char in default_value for char in ['{', '(', '<'])):
            default_value = None

        fields.append({
            'tag': tag,
            'name': field_name,
            'type': proto_type,
            'repeated': is_repeated,
            'default': default_value
        })

    fields.sort(key=lambda x: x['tag'])

    for oneof_group in oneof_groups.values():
        oneof_group.sort(key=lambda x: x['tag'])

    oneof_groups = {name: fields for name, fields in oneof_groups.items() if fields}

    return {
        'fields': fields,
        'oneof_groups': [{
            'name': name,
            'fields': fields
        } for name, fields in oneof_groups.items()],
        'nested_class_regions': nested_class_regions
    }

def extract_messages_from_csharp(content):
    classes = extract_class_definitions(content)
    messages = []
    all_enums = []

    class_map = {}
    nested_classes = defaultdict(list)

    for full_class_name, class_body in classes:
        parts = full_class_name.split('.')
        class_name = parts[-1]

        if len(parts) > 1:
            parent_name = '.'.join(parts[:-1])
            nested_classes[parent_name].append((full_class_name, class_body))
        else:
            class_map[full_class_name] = (class_body, [])

    for parent_name, nested_list in nested_classes.items():
        if parent_name in class_map:
            _, existing_nested = class_map[parent_name]
            existing_nested.extend(nested_list)
        else:
            class_map[parent_name] = (None, nested_list)

    for full_class_name, (class_body, nested_classes) in class_map.items():
        if class_body is None:
            continue

        class_info = extract_fields_from_class(class_body)
        nested_class_regions = class_info.get('nested_class_regions', [])

        nested_enums = extract_enums_from_content(
            class_body,
            full_class_name,
            exclude_regions=nested_class_regions
        )
        all_enums.extend(nested_enums)

        nested_messages = []
        for nested_full_name, nested_body in nested_classes:
            nested_info = extract_fields_from_class(nested_body)
            nested_nested_regions = nested_info.get('nested_class_regions', [])

            nested_class_enums = extract_enums_from_content(
                nested_body,
                nested_full_name,
                exclude_regions=nested_nested_regions
            )
            all_enums.extend(nested_class_enums)

            nested_name = nested_full_name.split('.')[-1]
            nested_messages.append({
                'full_name': nested_full_name,
                'name': nested_name,
                'fields': nested_info['fields'],
                'oneof_groups': nested_info['oneof_groups'],
                'nested_messages': [],
                'nested_enums': [e for e in nested_class_enums if e['parent_class'] == nested_full_name]
            })

        class_name = full_class_name.split('.')[-1]
        messages.append({
            'full_name': full_class_name,
            'name': class_name,
            'fields': class_info['fields'],
            'oneof_groups': class_info['oneof_groups'],
            'nested_messages': nested_messages,
            'nested_enums': [e for e in nested_enums if e['parent_class'] == full_class_name]
        })

    return all_enums, messages

def extract_top_level_enums(content):
    class_ranges = []
    class_pattern = re.compile(
        r'\[\s*global::ProtoBuf\.ProtoContract\s*[^\]]*\]\s*'
        r'public\s+partial\s+class\s+\w+\s*:\s*[^{]+\{',
        re.DOTALL
    )
    start_pos = 0
    while start_pos < len(content):
        class_match = class_pattern.search(content, start_pos)
        if not class_match:
            break
        class_start = class_match.start()
        class_end = find_matching_brace(content, class_match.start())
        if class_end > class_start:
            class_ranges.append((class_start, class_end))
            start_pos = class_end
        else:
            start_pos = class_match.end()

    enum_block_pattern = re.compile(
        r'\[\s*global::ProtoBuf\.ProtoContract[^\]]*\]\s*'
        r'public\s+enum\s+(\w+)\s*\{([^}]+)\}',
        re.DOTALL
    )

    item_pattern = re.compile(
        r'\[\s*global::ProtoBuf\.ProtoEnum[^\]]*Name\s*=\s*@?"([^"]+)"[^\]]*\]\s*'
        r'(\w+)\s*=\s*(\d+)'
    )

    plain_enum_pattern = re.compile(r'(\w+)\s*=\s*(\d+)\b')

    enums = []
    processed_enums = set()

    for enum_match in enum_block_pattern.finditer(content):
        in_class = False
        for (start, end) in class_ranges:
            if start <= enum_match.start() < end:
                in_class = True
                break
        if in_class:
            continue

        enum_name = enum_match.group(1)

        if enum_name in processed_enums:
            continue
        processed_enums.add(enum_name)

        enum_body = enum_match.group(2)
        enum_items = []
        used_values = set()

        for item_match in item_pattern.finditer(enum_body):
            proto_name = item_match.group(1)
            csharp_name = item_match.group(2)
            value = int(item_match.group(3))
            used_values.add(value)
            enum_items.append((proto_name, value))

        for plain_match in plain_enum_pattern.finditer(enum_body):
            csharp_name = plain_match.group(1)
            value = int(plain_match.group(2))
            if value in used_values:
                continue
            enum_items.append((csharp_name, value))

        enum_items.sort(key=lambda x: x[1])
        enums.append({
            'name': enum_name,
            'items': enum_items
        })

    return enums

def generate_proto(enums, messages):
    all_types = set(e['name'] for e in enums)
    for msg in messages:
        all_types.add(msg['name'])
        for nested in msg['nested_messages']:
            all_types.add(nested['name'])

    sorted_messages = []
    while messages:
        added = False
        for msg in messages[:]:
            dependencies = set()
            for field in msg['fields']:
                if field['type'] not in TYPE_MAPPING.values() and field['type'] in all_types:
                    dependencies.add(field['type'])
                if field['type'].startswith('map<'):
                    map_types = field['type'][4:-1].split(', ')
                    for map_type in map_types:
                        if map_type not in TYPE_MAPPING.values() and map_type in all_types:
                            dependencies.add(map_type)
            for oneof_group in msg.get('oneof_groups', []):
                for field in oneof_group['fields']:
                    if field['type'] not in TYPE_MAPPING.values() and field['type'] in all_types:
                        dependencies.add(field['type'])
            for nested_msg in msg['nested_messages']:
                for field in nested_msg['fields']:
                    if field['type'] not in TYPE_MAPPING.values() and field['type'] in all_types:
                        dependencies.add(field['type'])

            if not dependencies or all(dep in [m['name'] for m in sorted_messages] for dep in dependencies):
                sorted_messages.append(msg)
                messages.remove(msg)
                added = True

        if not added and messages:
            sorted_messages.append(messages.pop())

    proto_content = "syntax = \"proto3\";\n\n"

    for enum in enums:
        proto_content += f"enum {enum['name']} {{\n"
        for name, value in enum['items']:
            proto_content += f"    {name} = {value};\n"
        proto_content += "}\n\n"

    def generate_message(message, indent=0):
        indent_str = '    ' * indent
        content = f"{indent_str}message {message['name']} {{\n"

        for enum in message.get('nested_enums', []):
            enum_indent = '    ' * (indent + 1)
            content += f"\n{enum_indent}enum {enum['name']} {{\n"
            for name, value in enum['items']:
                content += f"{enum_indent}    {name} = {value};\n"
            content += f"{enum_indent}}}\n"

        for nested in message.get('nested_messages', []):
            nested_content = generate_message(nested, indent + 1)
            if nested_content.strip():
                content += "\n" + nested_content + "\n"

        for field in message.get('fields', []):
            field_indent = '    ' * (indent + 1)
            if field['repeated']:
                field_line = f"{field_indent}repeated {field['type']} {field['name']} = {field['tag']}"
            else:
                field_line = f"{field_indent}{field['type']} {field['name']} = {field['tag']}"

            if field['default'] and not any(char in field['default'] for char in ['<', '>', ':', '?', ';', '__pbn__']):
                default_str = field['default']
                if field['type'] == 'string' and not (default_str.startswith('"') or default_str.startswith("'")):
                    default_str = f'"{default_str}"'
                field_line += f" // default: {default_str}"

            content += field_line + ";\n"

        for oneof_group in message.get('oneof_groups', []):
            oneof_indent = '    ' * (indent + 1)
            content += f"{oneof_indent}oneof {oneof_group['name']} {{\n"

            for field in oneof_group['fields']:
                field_indent = '    ' * (indent + 2)
                field_line = f"{field_indent}{field['type']} {field['name']} = {field['tag']}"

                if field['default'] and not any(char in field['default'] for char in ['<', '>', ':', '?', ';']):
                    default_str = field['default']
                    if field['type'] == 'string' and not (default_str.startswith('"') or default_str.startswith("'")):
                        default_str = f'"{default_str}"'
                    field_line += f" // default: {default_str}"

                content += field_line + ";\n"

            content += f"{oneof_indent}}}\n"

        content += f"{indent_str}}}\n"
        return content

    for message in sorted_messages:
        proto_content += generate_message(message)
        proto_content += "\n"

    return proto_content

def convert_proto(content):
    top_level_enums = extract_top_level_enums(content)
    _, messages = extract_messages_from_csharp(content)

    all_enums = top_level_enums

    if not all_enums and not messages:
        print("No ProtoContract enumerations or message definitions were found in the file")
        return ""

    proto_content = generate_proto(all_enums, messages)

    return proto_content

if __name__ == "__main__":
    input_file_path = ".\\pbn_input\\testDataC.cs"
    output_file_path = "output.proto"

    with open(input_file_path, 'r', encoding='utf-8') as f:
        csharp_content = f.read()

    proto_content = convert_proto(csharp_content)

    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write(proto_content)

    print(f"成功生成 {output_file_path}")
