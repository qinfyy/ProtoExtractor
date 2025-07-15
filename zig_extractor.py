import re
import os

def parse_enums(content):
    enums = []
    enum_regex = r'pub\s+const\s+([A-Za-z0-9_]+)\s*=\s*enum\(i32\)\s*\{([\s\S]*?)\};'

    for match in re.finditer(enum_regex, content):
        enum_name = match.group(1)
        enum_content = match.group(2).strip()

        enum_items = []
        item_regex = r'([A-Za-z0-9_]+)\s*=\s*([0-9]+)'

        for item_match in re.finditer(item_regex, enum_content):
            enum_items.append({
                'name': item_match.group(1),
                'value': int(item_match.group(2))
            })

        enums.append({
            'name': enum_name,
            'items': enum_items
        })

    return enums

def parse_messages(content):
    messages = []
    oneof_fields_dict = {}
    map_messages = {}

    message_regex = r'pub\s+const\s+([A-Za-z0-9_]+)\s*=\s*struct\s*\{([\s\S]*?)pub\s+const\s+_desc_table\s*=\s*\.\{([\s\S]*?)\};'

    for match in re.finditer(message_regex, content):
        message_name = match.group(1)
        fields_content = match.group(2).strip()
        desc_table_content = match.group(3).strip()

        oneof_fields = {}

        union_regex = r'pub\s+const\s+([A-Za-z0-9_]+)\s*=\s*union\([^)]+\)\s*\{([\s\S]*?)pub\s+const\s+_union_desc\s*=\s*\.\{([\s\S]*?)\};'
        for union_match in re.finditer(union_regex, fields_content):
            union_name = union_match.group(1)
            union_content = union_match.group(2).strip()
            union_desc = union_match.group(3).strip()

            fields = []
            field_regex = r'([A-Za-z0-9_]+):\s*([^,\n]+)'
            for field_match in re.finditer(field_regex, union_content):
                field_name = field_match.group(1)
                field_type = field_match.group(2).strip()

                desc_regex = r'\.([A-Za-z0-9_]+)\s*=\s*fd\((\d+),\s*(.[^)]+)\)'
                for desc_match in re.finditer(desc_regex, union_desc):
                    if desc_match.group(1) == field_name:
                        field_number = int(desc_match.group(2))
                        field_type_info = desc_match.group(3)

                        proto_type = field_type
                        if 'FixedInt = .I32' in field_type_info:
                            if 'f32' in field_type:
                                proto_type = 'float'
                            elif 'i32' in field_type:
                                proto_type = 'sfixed32'
                            else:
                                proto_type = 'fixed32'
                        elif 'FixedInt = .I64' in field_type_info:
                            if 'f64' in field_type:
                                proto_type = 'double'
                            elif 'i64' in field_type:
                                proto_type = 'sfixed64'
                            else:
                                proto_type = 'fixed64'
                        elif 'Varint = .ZigZagOptimized' in field_type_info:
                            if 'i32' in field_type:
                                proto_type = 'sint32'
                            elif 'i64' in field_type:
                                proto_type = 'sint64'
                            else:
                                proto_type = 'sint64'
                        elif 'String' in field_type_info:
                            proto_type = 'string'
                        elif 'Bytes' in field_type_info:
                            proto_type = 'bytes'
                        elif field_type == 'f32':
                            proto_type = 'float'
                        elif field_type == 'f64':
                            proto_type = 'double'
                        else:
                            proto_type = convert_type_to_proto(field_type)

                        fields.append({
                            'name': field_name,
                            'type': proto_type,
                            'number': field_number
                        })
                        break

            oneof_fields[union_name] = fields

        fields = []
        field_regex = r'([A-Za-z0-9_]+):\s*([^=\n]+)(?:\s*=\s*[^,\n]+)?[,\n]'
        desc_regex = r'\.([A-Za-z0-9_]+)\s*=\s*fd\((\d+|\w+),\s*(.[^)]+)\)'

        field_list = []
        for field_match in re.finditer(field_regex, fields_content):
            field_name = field_match.group(1)
            field_type = field_match.group(2).strip()
            field_list.append((field_name, field_type))

        field_dict = dict(field_list)
        field_numbers = {}
        field_types = {}
        repeated_fields = {}
        oneof_union_types = {}
        packed_list_fields = {}

        for desc_match in re.finditer(desc_regex, desc_table_content):
            field_name = desc_match.group(1)
            field_number_str = desc_match.group(2)
            field_type_info = desc_match.group(3) if desc_match.group(3) else ''

            if field_number_str != 'null':
                field_numbers[field_name] = int(field_number_str)

            if '.List =' in field_type_info or '.PackedList =' in field_type_info:
                repeated_fields[field_name] = True
                if '.PackedList =' in field_type_info:
                    packed_list_fields[field_name] = True

            if field_name in field_dict:
                zig_field_type = field_dict[field_name]
                if zig_field_type == 'f32':
                    field_types[field_name] = 'float'
                elif zig_field_type == 'f64':
                    field_types[field_name] = 'double'
                elif 'ArrayList(f32)' in zig_field_type:
                    field_types[field_name] = 'float'
                elif 'ArrayList(f64)' in zig_field_type:
                    field_types[field_name] = 'double'

            if field_name not in field_types:
                if 'FixedInt = .I32' in field_type_info:
                    if field_name in field_dict:
                        field_type_match = field_dict[field_name]
                        if 'f32' in field_type_match:
                            field_types[field_name] = 'float'
                        elif 'i32' in field_type_match:
                            field_types[field_name] = 'sfixed32'
                        else:
                            field_types[field_name] = 'fixed32'
                elif 'FixedInt = .I64' in field_type_info:
                    if field_name in field_dict:
                        field_type_match = field_dict[field_name]
                        if 'f64' in field_type_match:
                            field_types[field_name] = 'double'
                        elif 'i64' in field_type_match:
                            field_types[field_name] = 'sfixed64'
                        else:
                            field_types[field_name] = 'fixed64'
                elif 'Varint = .ZigZagOptimized' in field_type_info:
                    if field_name in field_dict:
                        field_type_match = field_dict[field_name]
                        if 'i32' in field_type_match:
                            field_types[field_name] = 'sint32'
                        elif 'i64' in field_type_match:
                            field_types[field_name] = 'sint64'
                        else:
                            field_types[field_name] = 'sint64'
                elif 'String' in field_type_info:
                    field_types[field_name] = 'string'
                elif 'Bytes' in field_type_info:
                    field_types[field_name] = 'bytes'
                elif 'OneOf' in field_type_info:
                    union_type_match = re.search(r'OneOf\s*=\s*([A-Za-z0-9_]+)', field_type_info)
                    if union_type_match:
                        oneof_union_types[field_name] = union_type_match.group(1)

        if message_name.endswith('Entry') and len(field_list) == 2 and \
                field_list[0][0] == 'key' and field_list[1][0] == 'value':
            key_field_type = None
            value_field_type = None
            for desc_match in re.finditer(desc_regex, desc_table_content):
                field_name = desc_match.group(1)
                field_type_info = desc_match.group(3) if desc_match.group(3) else ''

                if field_name == 'key':
                    key_field_type = field_type_info
                elif field_name == 'value':
                    value_field_type = field_type_info

            key_type = field_list[0][1]
            if key_field_type:
                if 'FixedInt = .I32' in key_field_type:
                    if 'f32' in key_type:
                        key_type = 'float'
                    elif 'i32' in key_type:
                        key_type = 'sfixed32'
                    else:
                        key_type = 'fixed32'
                elif 'FixedInt = .I64' in key_field_type:
                    if 'f64' in key_type:
                        key_type = 'double'
                    elif 'i64' in key_type:
                        key_type = 'sfixed64'
                    else:
                        key_type = 'fixed64'
                elif 'Varint = .ZigZagOptimized' in key_field_type:
                    if 'i32' in key_type:
                        key_type = 'sint32'
                    elif 'i64' in key_type:
                        key_type = 'sint64'
                    else:
                        key_type = 'sint64'
            key_type = convert_type_to_proto(key_type)

            value_type = field_list[1][1]
            if value_field_type:
                if 'FixedInt = .I32' in value_field_type:
                    if 'f32' in value_type:
                        value_type = 'float'
                    elif 'i32' in value_type:
                        value_type = 'sfixed32'
                    else:
                        value_type = 'fixed32'
                elif 'FixedInt = .I64' in value_field_type:
                    if 'f64' in value_type:
                        value_type = 'double'
                    elif 'i64' in value_type:
                        value_type = 'sfixed64'
                    else:
                        value_type = 'fixed64'
                elif 'Varint = .ZigZagOptimized' in value_field_type:
                    if 'i32' in value_type:
                        value_type = 'sint32'
                    elif 'i64' in value_type:
                        value_type = 'sint64'
                    else:
                        value_type = 'sint64'
            value_type = convert_type_to_proto(value_type)

            map_messages[message_name] = (key_type, value_type)
            continue

        for field_name, field_type in field_list:
            if field_name in field_types:
                proto_type = field_types[field_name]
            else:
                proto_type = convert_type_to_proto(field_type)

            if field_name in repeated_fields:
                base_type = proto_type

                if field_name in packed_list_fields and base_type in ['int32', 'int64', 'uint32', 'uint64',
                                                                      'sint32', 'sint64', 'fixed32', 'fixed64',
                                                                      'sfixed32', 'sfixed64', 'float', 'double']:
                    proto_type = f'repeated {base_type}'
                else:
                    if base_type in ['string', 'bytes']:
                        proto_type = f'repeated {base_type}'
                    else:
                        proto_type = f'repeated {base_type}'

            if field_name in field_numbers:
                fields.append({
                    'name': field_name,
                    'type': proto_type,
                    'number': field_numbers[field_name]
                })
            elif field_name in oneof_union_types:
                fields.append({
                    'name': field_name,
                    'type': oneof_union_types[field_name],
                    'number': None,
                    'is_oneof': True
                })

        messages.append({
            'name': message_name,
            'fields': fields
        })

        if oneof_fields:
            oneof_fields_dict[message_name] = oneof_fields

    for message in messages:
        new_fields = []
        for field in message['fields']:
            if 'type' in field and isinstance(field['type'], str) and field['type'].startswith('repeated ') and field['type'].endswith('Entry'):
                entry_type = field['type'].replace('repeated ', '')
                if entry_type in map_messages:
                    key_type, value_type = map_messages[entry_type]
                    field['type'] = f'map<{key_type}, {value_type}>'
            new_fields.append(field)
        message['fields'] = new_fields

    return messages, oneof_fields_dict

def convert_type_to_proto(zig_type):
    base_type = zig_type.split('.')[-1].strip().lstrip('?')

    type_mapping = {
        'i32': 'int32',
        'i64': 'int64',
        'u32': 'uint32',
        'u64': 'uint64',
        'f32': 'float',
        'f64': 'double',
        'bool': 'bool',
        'ManagedString': 'string',
    }

    for zig, proto in type_mapping.items():
        if base_type.startswith(zig):
            return proto

    if base_type.startswith('ArrayList'):
        inner_type = re.search(r'ArrayList\(([^)]+)\)', base_type)
        if inner_type:
            inner_str = inner_type.group(1).strip()
            inner_proto = convert_type_to_proto(inner_str)
            if not inner_proto.startswith('repeated '):
                return f'repeated {inner_proto}'
            return inner_proto

    if zig_type.startswith('?'):
        return convert_type_to_proto(zig_type[1:])

    return base_type

def generate_proto_enums(enums):
    proto_output = ''
    for enum_def in enums:
        proto_output += f'enum {enum_def["name"]} {{\n'
        for item in enum_def['items']:
            proto_output += f'    {item["name"]} = {item["value"]};\n'
        proto_output += '}\n\n'
    return proto_output

def generate_proto_messages(messages, oneof_fields_dict):
    proto_output = ''
    for message in messages:
        proto_output += f'message {message["name"]} {{\n'

        oneof_groups = {}
        regular_fields = []

        for field in message['fields']:
            if field.get('is_oneof', False):
                oneof_name = field['name']
                union_type = field['type']

                if message['name'] in oneof_fields_dict:
                    message_oneof_fields = oneof_fields_dict[message['name']]
                    if union_type in message_oneof_fields:
                        oneof_groups[oneof_name] = message_oneof_fields[union_type]
            else:
                regular_fields.append(field)

        for field in sorted(regular_fields, key=lambda x: x['number']):
            field_type = field['type']
            if field_type.startswith('repeated '):
                proto_output += f'    repeated {field_type.replace("repeated ", "")} {field["name"]} = {field["number"]};\n'
            else:
                proto_output += f'    {field_type} {field["name"]} = {field["number"]};\n'

        for oneof_name, fields in oneof_groups.items():
            clean_oneof_name = oneof_name.replace("_union", "")
            proto_output += f'    oneof {clean_oneof_name} {{\n'
            for field in sorted(fields, key=lambda x: x['number']):
                proto_output += f'        {field["type"]} {field["name"]} = {field["number"]};\n'
            proto_output += '    }\n'

        proto_output += '}\n\n'
    return proto_output

def convert_proto(content):
    clean_content = re.sub(r'//.*', '', content)
    clean_content = re.sub(r'/\*.*?\*/', '', clean_content, flags=re.DOTALL)

    enums = parse_enums(clean_content)
    messages, oneof_fields_dict = parse_messages(clean_content)

    proto_output = 'syntax = "proto3";\n\n'
    proto_output += generate_proto_enums(enums)
    proto_output += generate_proto_messages(messages, oneof_fields_dict)

    return proto_output


if __name__ == '__main__':
    file_path = os.path.join(os.path.dirname(__file__), 'testDataC.pb.zig')
    output_path = os.path.join(os.path.dirname(__file__), 'output.proto')

    with open(file_path, 'r', encoding='utf-8') as f:
        file_content = f.read()

    proto_output = convert_proto(file_content)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(proto_output)

    print('已经写到 output.proto 文件')
