import re
from typing import Dict, Optional, Set

BASE_TYPES = {'int32', 'sint32', 'uint32', 'fixed32', 'sfixed32',
              'int64', 'sint64', 'uint64', 'fixed64', 'sfixed64',
              'bool', 'string', 'bytes', 'float', 'double'}

def extract_definitions(python_code: str):
    enums: Dict[str, dict] = {}
    messages: Dict[str, dict] = {}

    clean_code = remove_comments(python_code)

    enum_pattern = re.compile(
        r'class\s+(\w+)\(betterproto\.Enum\):(.*?)(?=(?:^\s*(?:class|@dataclass)|\Z))',
        re.DOTALL | re.MULTILINE
    )
    for enum_name, enum_body in enum_pattern.findall(clean_code):
        items = []
        enum_item_pattern = re.compile(r'\s+(\w+)\s*=\s*(\d+)')
        for match in enum_item_pattern.finditer(enum_body):
            items.append((match.group(1), int(match.group(2))))
        enums[enum_name] = {
            'name': enum_name,
            'items': items
        }

    message_pattern = re.compile(
        r'@dataclass\s+class\s+(\w+)\(betterproto\.Message\):(.*?)(?=(?:@dataclass|class|\Z))',
        re.DOTALL | re.MULTILINE
    )
    for msg_name, msg_body in message_pattern.findall(clean_code):
        fields = parse_message_fields(msg_body)
        nested_msgs = parse_nested_definitions(msg_body)
        nested_enums = parse_nested_enums(msg_body)
        messages[msg_name] = {
            'name': msg_name,
            'fields': fields,
            'nested_messages': nested_msgs,
            'nested_enums': nested_enums
        }

    return enums, messages

def remove_comments(code: str):
    lines = []
    for line in code.split('\n'):
        if line.strip().startswith('#'):
            continue
        lines.append(line)
    return '\n'.join(lines)

def parse_message_fields(message_body: str):
    fields = []
    oneof_pattern = re.compile(r'group\s*=\s*"(\w+)"')

    assignment_pattern = re.compile(
        r'(\w+)\s*:\s*([^\n=]+?)\s*=\s*\(*\s*betterproto\.(\w+)_field\s*\((.*?)\)\s*\)*',
        re.DOTALL
    )

    for match in assignment_pattern.finditer(message_body):
        field_name = match.group(1)
        type_annotation = match.group(2).strip().strip('"\'')
        field_type = match.group(3)
        param_str = match.group(4).replace('\n', ' ')
        params = [p.strip() for p in param_str.split(',') if p.strip()]
        if not params:
            continue

        field_number = int(params[0])
        oneof_group = None
        oneof_match = oneof_pattern.search(param_str)
        if oneof_match:
            oneof_group = oneof_match.group(1)

        is_map = field_type == "map"
        is_repeated = "List[" in type_annotation or "repeated" in type_annotation
        is_oneof = oneof_group is not None

        if is_map:
            key_type = params[1].replace("betterproto.TYPE_", "").lower()
            value_type = params[2].replace("betterproto.TYPE_", "").lower()

            value_type_hint = re.search(
                r'Dict\[\s*[\w\.]+\s*,\s*["\']?([\w\.]+)["\']?\s*\]',
                match.group(0)
            )

            if value_type_hint:
                hint = value_type_hint.group(1)
                if value_type in ("enum", "message"):
                    value_type = hint
                elif value_type == "enum":
                    value_type = hint

            fields.append({
                'name': field_name,
                'proto_type': f"map<{key_type}, {value_type}>",
                'field_number': field_number,
                'is_map': True,
                'map_key_type': key_type,
                'map_value_type': value_type,
                'is_oneof': is_oneof,
                'oneof_group': oneof_group
            })

            continue

        base_type = type_annotation
        if "List[" in type_annotation:
            m = re.search(r'List\[\s*["\']?([\w\.]+)["\']?\s*\]', type_annotation)
            if m:
                base_type = m.group(1)

        proto_type = proto_to_native_type(field_type, base_type)
        fields.append({
            'name': field_name,
            'proto_type': proto_type,
            'field_number': field_number,
            'is_repeated': is_repeated,
            'is_oneof': is_oneof,
            'oneof_group': oneof_group
        })

    return fields

def parse_nested_definitions(message_body: str):
    nested = {}
    nested_pattern = re.compile(
        r'@dataclass\s+class\s+(\w+)\(betterproto\.Message\):([\s\S]*?)(?=(?:@dataclass|class|$))',
        re.DOTALL
    )
    for name, body in nested_pattern.findall(message_body):
        nested[name] = {
            'name': name,
            'fields': parse_message_fields(body),
            'nested_messages': parse_nested_definitions(body),
            'nested_enums': parse_nested_enums(body)
        }
    return nested

def parse_nested_enums(message_body: str):
    enums = {}
    enum_pattern = re.compile(
        r'class\s+(\w+)\(betterproto\.Enum\):([\s\S]*?)(?=(?:^\s*(?:class|@dataclass)|$))',
        re.DOTALL | re.MULTILINE
    )
    for enum_name, enum_body in enum_pattern.findall(message_body):
        items = []
        enum_item_pattern = re.compile(r'\s+(\w+)\s*=\s*(\d+)')
        for match in enum_item_pattern.finditer(enum_body):
            items.append((match.group(1), int(match.group(2))))
        enums[enum_name] = {
            'name': enum_name,
            'items': items
        }
    return enums

def proto_to_native_type(proto_field_type: str, type_annotation: Optional[str]):
    type_mapping = {
        "int32": "int32",
        "sint32": "sint32",
        "uint32": "uint32",
        "fixed32": "fixed32",
        "sfixed32": "sfixed32",
        "int64": "int64",
        "sint64": "sint64",
        "uint64": "uint64",
        "fixed64": "fixed64",
        "sfixed64": "sfixed64",
        "bool": "bool",
        "string": "string",
        "bytes": "bytes",
        "float": "float",
        "double": "double",
        "enum": type_annotation or "int32",
        "message": type_annotation or "UnknownMessage"
    }

    if type_annotation:
        type_annotation = type_annotation.strip().strip('"').strip("'")

    return type_mapping.get(proto_field_type, type_annotation or "unknown")

def generate_proto_file(enums: Dict[str, dict], messages: Dict[str, dict]):
    output = ['syntax = "proto3";\n']
    all_definitions = []

    for enum in enums.values():
        all_definitions.append(("enum", enum['name'], enum))

    for msg in messages.values():
        collect_definitions(msg, all_definitions)

    def definition_sort_key(item):
        if item[0] == "enum":
            return (0, item[1])
        else:
            return (1, item[1])

    sorted_definitions = sorted(all_definitions, key=definition_sort_key)

    type_mapping = {}
    type_names = set()

    for def_type, name, obj in sorted_definitions:
        type_names.add(name)
        lower_name = name.lower()
        if lower_name not in type_mapping:
            type_mapping[lower_name] = []
        type_mapping[lower_name].append(name)

    for def_type, _, obj in sorted_definitions:
        if def_type == "enum":
            generate_enum(output, obj)
        else:
            generate_message(output, obj, type_mapping, type_names)

    return "\n".join(output)

def collect_definitions(msg: dict, definitions: list):
    definitions.append(("message", msg['name'], msg))

    for enum in msg['nested_enums'].values():
        definitions.append(("enum", enum['name'], enum))

    for nested_msg in msg['nested_messages'].values():
        collect_definitions(nested_msg, definitions)

def generate_enum(output: list, enum: dict):
    output.append(f"enum {enum['name']} {{")
    for name, val in enum['items']:
        output.append(f"    {name} = {val};")
    output.append("}\n")

def resolve_type(type_name: str, type_mapping: Dict, type_names: Set[str]):
    if type_name.lower() in BASE_TYPES:
        return type_name

    if type_name in type_names:
        return type_name

    lower_name = type_name.lower()
    candidates = type_mapping.get(lower_name, [])

    if len(candidates) == 1:
        return candidates[0]

    return type_name

def generate_message(output: list, msg: dict, type_mapping: Dict, type_names: Set[str], indent: int = 0):
    ind = "    " * indent
    output.append(f"{ind}message {msg['name']} {{")

    for enum in msg['nested_enums'].values():
        output.append(f"{ind}    enum {enum['name']} {{")
        for name, val in enum['items']:
            output.append(f"{ind}        {name} = {val};")
        output.append(f"{ind}    }}")
        output.append("")

    for nested in msg['nested_messages'].values():
        generate_message(output, nested, type_mapping, type_names, indent + 1)

    oneof_groups = {}
    for field in msg['fields']:
        if field.get('is_oneof') and field.get('oneof_group'):
            group_name = field['oneof_group']
            if group_name not in oneof_groups:
                oneof_groups[group_name] = []
            oneof_groups[group_name].append(field)

    for field in msg['fields']:
        if field.get('is_oneof') or field.get('is_map'):
            continue

        original_type = field['proto_type']
        resolved_type = resolve_type(original_type, type_mapping, type_names)

        prefix = "repeated " if field.get('is_repeated') else ""
        output.append(f"{ind}    {prefix}{resolved_type} {field['name']} = {field['field_number']};")

    for field in msg['fields']:
        if field.get('is_map'):
            resolved_value_type = resolve_type(field['map_value_type'], type_mapping, type_names)
            output.append(f"{ind}    map<{field['map_key_type']}, {resolved_value_type}> {field['name']} = {field['field_number']};")

    for group_name, group_fields in oneof_groups.items():
        output.append(f"{ind}    oneof {group_name} {{")
        for field in group_fields:
            resolved_type = resolve_type(field['proto_type'], type_mapping, type_names)
            output.append(f"{ind}        {resolved_type} {field['name']} = {field['field_number']};")

        output.append(f"{ind}    }}")

    output.append(f"{ind}}}\n")

def convert_proto(python_code):
    enums, messages = extract_definitions(python_code)
    proto = generate_proto_file(enums, messages)
    return proto

if __name__ == '__main__':
    with open(".\\betterproto_input\\testDataC.py", "r", encoding="utf-8") as f:
        code = f.read()

    proto = convert_proto(code)

    with open("output.proto", "w", encoding="utf-8") as f:
        f.write(proto)

    print('已写入文件 output.proto')
