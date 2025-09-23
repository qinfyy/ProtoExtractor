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

    # 匹配消息结构，包括嵌套结构
    message_regex = r'pub\s+const\s+([A-Za-z0-9_]+)\s*=\s*struct\s*\{([\s\S]*?)pub\s+const\s+_desc_table\s*=\s*\.\{([\s\S]*?)\};'

    # 第一遍，收集所有 map 入口消息
    for match in re.finditer(message_regex, content):
        message_name = match.group(1)
        fields_content = match.group(2).strip()
        desc_table_content = match.group(3).strip()

        # 检查这是否是 map
        field_regex = r'([A-Za-z0-9_]+):\s*([^=\n]+)(?:\s*=\s*[^,\n]+)?[,\n]'
        field_list = []
        for field_match in re.finditer(field_regex, fields_content):
            field_name = field_match.group(1)
            field_type = field_match.group(2).strip()
            field_list.append((field_name, field_type))

        if message_name.endswith('Entry') and len(field_list) == 2 and \
                field_list[0][0] == 'key' and field_list[1][0] == 'value':
            desc_regex = r'\.([A-Za-z0-9_]+)\s*=\s*fd\((\d+|\w+),\s*(.[^)]+)\)'
            key_field_type_info = None
            value_field_type_info = None
            for desc_match in re.finditer(desc_regex, desc_table_content):
                field_name = desc_match.group(1)
                field_type_info = desc_match.group(3) if desc_match.group(3) else ''
                if field_name == 'key':
                    key_field_type_info = field_type_info
                elif field_name == 'value':
                    value_field_type_info = field_type_info

            key_zig_type = field_list[0][1]
            value_zig_type = field_list[1][1]

            # 转换 key 类型
            key_proto_type = key_zig_type
            if key_field_type_info:
                if 'FixedInt = .I32' in key_field_type_info:
                    if 'f32' in key_zig_type:
                        key_proto_type = 'float'
                    elif 'i32' in key_zig_type:
                        key_proto_type = 'sfixed32'
                    else:
                        key_proto_type = 'fixed32'
                elif 'FixedInt = .I64' in key_field_type_info:
                    if 'f64' in key_zig_type:
                        key_proto_type = 'double'
                    elif 'i64' in key_zig_type:
                        key_proto_type = 'sfixed64'
                    else:
                        key_proto_type = 'fixed64'
                elif 'Varint = .ZigZagOptimized' in key_field_type_info:
                    if 'i32' in key_zig_type:
                        key_proto_type = 'sint32'
                    elif 'i64' in key_zig_type:
                        key_proto_type = 'sint64'
                    else:
                        key_proto_type = 'sint64'
            key_proto_type = convert_type_to_proto(key_proto_type)

            # 转换 value 类型
            value_proto_type = value_zig_type
            if value_field_type_info:
                if 'FixedInt = .I32' in value_field_type_info:
                    if 'f32' in value_zig_type:
                        value_proto_type = 'float'
                    elif 'i32' in value_zig_type:
                        value_proto_type = 'sfixed32'
                    else:
                        value_proto_type = 'fixed32'
                elif 'FixedInt = .I64' in value_field_type_info:
                    if 'f64' in value_zig_type:
                        value_proto_type = 'double'
                    elif 'i64' in value_zig_type:
                        value_proto_type = 'sfixed64'
                    else:
                        value_proto_type = 'fixed64'
                elif 'Varint = .ZigZagOptimized' in value_field_type_info:
                    if 'i32' in value_zig_type:
                        value_proto_type = 'sint32'
                    elif 'i64' in value_zig_type:
                        value_proto_type = 'sint64'
                    else:
                        value_proto_type = 'sint64'
            value_proto_type = convert_type_to_proto(value_proto_type)

            map_messages[message_name] = (key_proto_type, value_proto_type)
        # 注意：不会跳过这里；将在第二遍处理所有消息

    # 第二遍，解析所有消息,包括非Entry
    for match in re.finditer(message_regex, content):
        message_name = match.group(1)
        fields_content = match.group(2).strip()
        desc_table_content = match.group(3).strip()

        #跳过最终输出中的 map 条目消息
        field_regex = r'([A-Za-z0-9_]+):\s*([^=\n]+)(?:\s*=\s*[^,\n]+)?[,\n]'
        field_list = []
        for field_match in re.finditer(field_regex, fields_content):
            field_name = field_match.group(1)
            field_type = field_match.group(2).strip()
            field_list.append((field_name, field_type))

        if message_name.endswith('Entry') and len(field_list) == 2 and \
                field_list[0][0] == 'key' and field_list[1][0] == 'value':
            continue  # 跳过输出中的 map 条目消息

        # 解析 oneof
        oneof_fields = {}
        union_regex = r'pub\s+const\s+([A-Za-z0-9_]+)\s*=\s*union\([^)]+\)\s*\{([\s\S]*?)pub\s+const\s+_union_desc\s*=\s*\.\{([\s\S]*?)\};'
        for union_match in re.finditer(union_regex, fields_content):
            union_name = union_match.group(1)
            union_content = union_match.group(2).strip()
            union_desc = union_match.group(3).strip()

            fields = []
            field_regex_inner = r'([A-Za-z0-9_]+):\s*([^,\n]+)'
            for field_match in re.finditer(field_regex_inner, union_content):
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

        # 解析字段类型和数字
        field_dict = dict(field_list)
        field_numbers = {}
        field_types = {}
        repeated_fields = {}
        oneof_union_types = {}
        packed_list_fields = {}

        desc_regex = r'\.([A-Za-z0-9_]+)\s*=\s*fd\((\d+|\w+),\s*(.[^)]+)\)'
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

        # 构建字段列表
        fields = []
        for field_name, field_type in field_list:
            is_map = False
            final_type = None

            list_match = re.match(r'ArrayList\(\s*([A-Za-z0-9_.]+)\s*\)', field_type)
            if list_match:
                full_entry_name = list_match.group(1)
                # 尝试截取'.' 之后的最后一部分
                simple_entry_name = full_entry_name.split('.')[-1]
                if simple_entry_name in map_messages:
                    is_map = True
                    k, v = map_messages[simple_entry_name]
                    final_type = f'map<{k}, {v}>'

            if not is_map:
                if field_name in field_types:
                    base_type = field_types[field_name]
                else:
                    base_type = convert_type_to_proto(field_type)

                if field_name in repeated_fields:
                    if field_name in packed_list_fields and base_type in [
                        'int32', 'int64', 'uint32', 'uint64',
                        'sint32', 'sint64', 'fixed32', 'fixed64',
                        'sfixed32', 'sfixed64', 'float', 'double'
                    ]:
                        final_type = f'repeated {base_type}'
                    else:
                        final_type = f'repeated {base_type}'
                else:
                    final_type = base_type

            if field_name in field_numbers:
                fields.append({
                    'name': field_name,
                    'type': final_type,
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

    return messages, oneof_fields_dict

def convert_type_to_proto(zig_type):
    clean_type = zig_type.lstrip('?')
    base_type = clean_type.split('.')[-1].strip()

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

    # 处理 ArrayList
    if base_type.startswith('ArrayList'):
        inner_match = re.search(r'ArrayList\(([^)]+)\)', base_type)
        if inner_match:
            inner = inner_match.group(1).strip()
            inner_proto = convert_type_to_proto(inner)
            if not inner_proto.startswith('repeated '):
                return inner_proto
            return inner_proto

    # 直接返回自定义类型
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
                    msg_oneof = oneof_fields_dict[message['name']]
                    if union_type in msg_oneof:
                        oneof_groups[oneof_name] = msg_oneof[union_type]
            else:
                regular_fields.append(field)

        # 输出普通字段
        for field in sorted(regular_fields, key=lambda x: x['number']):
            proto_output += f'    {field["type"]} {field["name"]} = {field["number"]};\n'

        # 输出 oneof 组
        for oneof_name, fields in oneof_groups.items():
            clean_name = oneof_name.replace("_union", "")
            proto_output += f'    oneof {clean_name} {{\n'
            for field in sorted(fields, key=lambda x: x['number']):
                proto_output += f'        {field["type"]} {field["name"]} = {field["number"]};\n'
            proto_output += '    }\n'

        proto_output += '}\n\n'
    return proto_output

def convert_proto(content):
    # 删除注释
    clean_content = re.sub(r'//.*', '', content)
    clean_content = re.sub(r'/\*.*?\*/', '', clean_content, flags=re.DOTALL)

    enums = parse_enums(clean_content)
    messages, oneof_fields_dict = parse_messages(clean_content)

    proto_output = 'syntax = "proto3";\n\n'
    proto_output += generate_proto_enums(enums)
    proto_output += generate_proto_messages(messages, oneof_fields_dict)

    return proto_output

if __name__ == '__main__':
    file_path = "D:\\Project\\Code2Protobuf\\input\\zig\\testDataD.pb.zig"
    output_path = "D:\\Project\\Code2Protobuf\\output\\output.proto"

    with open(file_path, 'r', encoding='utf-8') as f:
        file_content = f.read()

    proto_output = convert_proto(file_content)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(proto_output)

    print('已经写到 output.proto 文件')
