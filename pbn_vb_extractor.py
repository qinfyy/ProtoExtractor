import re
from collections import defaultdict

def is_line_commented(content, position):
    # 找到行首
    line_start = content.rfind('\n', 0, position) + 1
    if line_start < 0:
        line_start = 0

    # 找到行尾
    line_end = content.find('\n', position)
    if line_end == -1:
        line_end = len(content)

    # 提取整行内容
    line_content = content[line_start:line_end]

    # 处理字符串中的引号转义
    in_string = False
    string_start_char = None
    i = 0
    while i < len(line_content):
        char = line_content[i]

        # 处理字符串开始/结束
        if not in_string:
            # 检查字符串开始
            if char in ['"', '“', '”']:
                in_string = True
                string_start_char = char
        else:
            # 处理字符串内的转义引号
            if char == string_start_char:
                # 检查是否是转义的引号
                if i + 1 < len(line_content) and line_content[i+1] == string_start_char:
                    i += 1  # 跳过转义引号
                else:
                    in_string = False
                    string_start_char = None
            # 处理不同引号类型的字符串结束
            elif string_start_char == '"' and char in ['“', '”']:
                # 半角引号字符串中包含全角引号，不结束字符串
                pass
            elif string_start_char in ['“', '”'] and char == '"':
                # 全角引号字符串中包含半角引号，不结束字符串
                pass

        # 检查注释符号（不在字符串中）
        if not in_string:
            # 检查所有可能的注释符号
            if char in ["'", "‘", "’"]:
                # 找到注释位置
                comment_pos = line_start + i
                # 如果注释位置在目标位置之前，则该行被注释
                if comment_pos <= position:
                    return True

        i += 1

    return False

def convert_type(type_str, data_format=None, base_type=None):
    type_str = type_str.replace('Global.', '').replace('System.', '').strip()
    type_str = type_str.replace(' ', '')

    # 处理字节数组
    if type_str == 'Byte()':
        return 'bytes'

    # 基本类型映射
    type_map = {
        'Integer': 'int32',
        'Long': 'int64',
        'UInteger': 'uint32',
        'ULong': 'uint64',
        'Single': 'float',
        'Double': 'double',
        'Boolean': 'bool',
        'String': 'string'
    }

    # 处理数组类型
    if type_str.endswith('()'):
        inner = type_str[:-2]

        if data_format == 'ZigZag':
            if inner == 'Integer':
                return 'repeated sint32'
            elif inner == 'Long':
                return 'repeated sint64'
        elif data_format == 'FixedSize':
            if inner == 'Integer':
                return 'repeated sfixed32'
            elif inner == 'Long':
                return 'repeated sfixed64'
            elif inner == 'UInteger':
                return 'repeated fixed32'
            elif inner == 'ULong':
                return 'repeated fixed64'

        inner_type = type_map.get(inner, inner)
        return 'repeated ' + inner_type

    # DataFormat.ZigZag（sint）
    if data_format == 'ZigZag' and base_type:
        if base_type == 'Integer':
            return 'sint32'
        elif base_type == 'Long':
            return 'sint64'

    # DataFormat.FixedSize（fixed/sfixed）
    if data_format == 'FixedSize' and base_type:
        if base_type == 'Integer':
            return 'sfixed32'
        elif base_type == 'Long':
            return 'sfixed64'
        elif base_type == 'UInteger':
            return 'fixed32'
        elif base_type == 'ULong':
            return 'fixed64'

    if type_str in type_map:
        return type_map[type_str]

    # 处理列表类型 (List(Of T))
    if 'List(Of' in type_str:
        match = re.search(r'List\(Of\s*([^)]+)\)', type_str)
        if match:
            inner = match.group(1).strip()
            # repeated bytes
            if inner == 'Byte()' or inner == 'Byte(':
                return 'repeated bytes'
            inner_type = convert_type(inner)
            return 'repeated ' + inner_type

    # 处理字典类型 (Dictionary(Of K, V)) - 这里不直接转换，返回原始信息
    if 'Dictionary(Of' in type_str:
        return type_str

    # 去除嵌套类型的外部类前缀
    if '.' in type_str:
        type_str = type_str.split('.')[-1]

    # 其他的消息或枚举
    return type_str

def convert_dictionary_type(type_str, key_format=None, value_format=None):
    # 提取Dictionary中的类型
    match = re.search(r'Dictionary\(Of\s*([^,]+),\s*([^)]+)\)', type_str)
    if match:
        key_type = match.group(1).strip()
        value_type = match.group(2).strip()

        # 转换key类型
        converted_key = convert_type(key_type, key_format, key_type)

        # 转换value类型
        converted_value = convert_type(value_type, value_format, value_type)

        return 'map<' + converted_key + ', ' + converted_value + '>'

    return type_str

def find_matching_end(content, start_pos, start_keyword, end_keyword):
    level = 1
    pos = start_pos

    start_pattern = re.compile(r'\b' + start_keyword + r'\b', re.IGNORECASE)
    end_pattern = re.compile(r'\b' + end_keyword + r'\b', re.IGNORECASE)

    while level > 0 and pos < len(content):
        # 查找下一个开始或结束
        start_match = start_pattern.search(content, pos)
        end_match = end_pattern.search(content, pos)

        if not end_match:
            return -1

        if start_match and start_match.start() < end_match.start():
            level += 1
            pos = start_match.end()
        else:
            level -= 1
            if level == 0:
                return end_match.end()
            pos = end_match.end()

    return -1

def parse_vb_class(class_content, indent=0, content_cache=None):
    indent_str = "    " * indent
    lines = []

    # 提取类名
    class_name_match = re.search(r'(?:Partial\s+)?Public\s+Class\s+(\w+)', class_content, re.IGNORECASE)
    if not class_name_match:
        return ""

    class_name = class_name_match.group(1)
    lines.append(f"{indent_str}message {class_name} {{")

    # 找到类体的精确边界
    class_start = class_name_match.end()

    # 找到最外层的 End Class
    end_class_matches = list(re.finditer(r'End\s+Class', class_content, re.IGNORECASE))
    class_end_pos = end_class_matches[-1].start() if end_class_matches else len(class_content)

    body = class_content[class_start:class_end_pos]

    # 识别oneof组
    oneof_groups = {}
    oneof_pattern = re.compile(
        r'Private\s+(\w+)\s+As\s+Global\.ProtoBuf\.DiscriminatedUnion\w*\b',
        re.IGNORECASE | re.DOTALL
    )
    for match in oneof_pattern.finditer(body):
        field_name = match.group(1)
        group_name = re.sub(r'^__pbn__', '', field_name)
        oneof_groups[field_name] = group_name

    # 收集所有嵌套定义
    nested_definitions = []

    # 先查找所有的ProtoContract标记
    proto_contract_pattern = re.compile(
        r'<Global\.ProtoBuf\.ProtoContract[^>]*>\s*_',
        re.IGNORECASE | re.DOTALL
    )

    # 查找每个ProtoContract之后的类或枚举定义
    for contract_match in proto_contract_pattern.finditer(body):
        start = contract_match.start()
        # 在ProtoContract之后查找类或枚举
        rest_content = body[contract_match.end():]

        # 查找类定义
        class_match = re.match(r'\s*(?:Partial\s+)?Public\s+Class\s+(\w+)', rest_content, re.IGNORECASE | re.DOTALL)
        if class_match:
            name = class_match.group(1)
            # 找到对应的End Class
            end = find_matching_end(body, contract_match.end() + class_match.end(), 'Class', 'End\\s+Class')
            if end != -1:
                nested_definitions.append({
                    'type': 'class',
                    'name': name,
                    'start': start,
                    'end': end,
                    'content': body[start:end]
                })
                continue

        # 查找枚举定义
        enum_match = re.match(r'\s*Public\s+Enum\s+(\w+)', rest_content, re.IGNORECASE | re.DOTALL)
        if enum_match:
            name = enum_match.group(1)
            # 找到对应的End Enum
            end_enum_match = re.search(r'End\s+Enum', body[contract_match.end():], re.IGNORECASE)
            if end_enum_match:
                end = contract_match.end() + end_enum_match.end()
                nested_definitions.append({
                    'type': 'enum',
                    'name': name,
                    'start': start,
                    'end': end,
                    'content': body[start:end]
                })

    # 排序并去重嵌套定义
    nested_definitions.sort(key=lambda x: x['start'])

    # 去除重叠的定义
    filtered_nested = []
    prev_end = -1
    for nested in nested_definitions:
        if nested['start'] >= prev_end:
            filtered_nested.append(nested)
            prev_end = nested['end']

    nested_ranges = [(item['start'], item['end']) for item in filtered_nested]

    # 处理字段
    fields = []
    oneof_fields = defaultdict(list)
    processed_tags = set()

    # 匹配所有 ProtoMember
    protomember_pattern = re.compile(
        r'<Global\.ProtoBuf\.ProtoMember\((\d+)[^)]*\)[^>]*>',
        re.IGNORECASE
    )

    protomember_matches = list(protomember_pattern.finditer(body))

    for i, protomember_match in enumerate(protomember_matches):
        tag = int(protomember_match.group(1))
        if tag in processed_tags:
            continue

        # 检查是否在嵌套定义内
        pos = protomember_match.start()
        in_nested = any(start <= pos < end for start, end in nested_ranges)
        if in_nested:
            continue

        if is_line_commented(body, pos):
            continue

        # 确定搜索范围
        start_pos = protomember_match.start()
        next_boundary = len(body)

        if i + 1 < len(protomember_matches):
            next_boundary = min(next_boundary, protomember_matches[i + 1].start())

        for start, end in nested_ranges:
            if start > pos:
                next_boundary = min(next_boundary, start)
                break

        member_text = body[start_pos:next_boundary]

        # 提取属性信息
        prop_pattern = re.compile(
            r'Public\s+(?:ReadOnly\s+)?Property\s+(\w+)\s+As\s+(?:New\s+)?([^\r\n]+?)(?:\s*=\s*[^\r\n]+)?(?:\s*\r?\n|$)',
            re.IGNORECASE | re.DOTALL
        )

        prop_match = prop_pattern.search(member_text)
        if not prop_match:
            continue

        field_name = prop_match.group(1)
        type_str = prop_match.group(2).strip()

        # 提取Name参数
        name_match = re.search(r'Name\s*:=\s*"([^"]+)"', member_text)
        proto_name = name_match.group(1) if name_match else field_name

        # 提取DataFormat参数
        data_format_match = re.search(r'DataFormat\s*:=\s*Global\.ProtoBuf\.DataFormat\.(\w+)', member_text)
        data_format = data_format_match.group(1) if data_format_match else None

        # 处理类型
        if 'Dictionary(Of' in type_str:
            key_format_match = re.search(r'KeyFormat\s*:=\s*Global\.ProtoBuf\.DataFormat\.(\w+)', member_text)
            key_format = key_format_match.group(1) if key_format_match else None

            value_format_match = re.search(r'ValueFormat\s*:=\s*Global\.ProtoBuf\.DataFormat\.(\w+)', member_text)
            value_format = value_format_match.group(1) if value_format_match else None

            converted_type = convert_dictionary_type(type_str, key_format, value_format)
        else:
            base_type = type_str.replace('()', '').strip() if type_str.endswith('()') else type_str
            converted_type = convert_type(type_str, data_format, base_type)

        # 检查是否是oneof字段
        is_oneof = False
        if 'Get' in member_text and 'End Get' in member_text:
            for oneof_var, group_name in oneof_groups.items():
                if re.search(r'\b' + re.escape(oneof_var) + r'\b', member_text):
                    is_oneof = True
                    oneof_fields[group_name].append((tag, proto_name, converted_type))
                    processed_tags.add(tag)
                    break

        if not is_oneof:
            fields.append((tag, proto_name, converted_type))
            processed_tags.add(tag)

    # 输出字段
    fields.sort(key=lambda x: x[0])
    for tag, proto_name, converted_type in fields:
        lines.append(f"{indent_str}    {converted_type} {proto_name} = {tag};")

    # 输出oneof
    for group_name, oneof_field_list in oneof_fields.items():
        lines.append(f"{indent_str}    oneof {group_name} {{")
        oneof_field_list.sort(key=lambda x: x[0])
        for tag, name, type_str in oneof_field_list:
            lines.append(f"{indent_str}        {type_str} {name} = {tag};")
        lines.append(f"{indent_str}    }}")

    # 添加空行
    if (fields or oneof_fields) and filtered_nested:
        lines.append("")

    # 处理嵌套定义
    for nested in filtered_nested:
        if nested['type'] == 'class':
            nested_content = parse_vb_class(nested['content'], indent + 1, content_cache)
            # 将嵌套内容分割成行并添加到当前列表
            if nested_content:
                lines.extend(nested_content.splitlines())
        elif nested['type'] == 'enum':
            nested_content = parse_vb_enum(nested['content'], indent + 1)
            if nested_content:
                lines.extend(nested_content.splitlines())

    lines.append(f"{indent_str}}}")
    lines.append("")

    return "\n".join(lines)

def parse_vb_enum(enum_content, indent=0):
    indent_str = "    " * indent
    lines = []

    # 提取枚举名
    enum_name_match = re.search(r'Public\s+Enum\s+(\w+)', enum_content, re.IGNORECASE)
    if not enum_name_match:
        return ""

    enum_name = enum_name_match.group(1)
    lines.append(f"{indent_str}enum {enum_name} {{")

    # 查找枚举体的开始和结束
    enum_body_start = enum_name_match.end()
    enum_body_end = re.search(r'End\s+Enum', enum_content, re.IGNORECASE)
    if enum_body_end:
        enum_body = enum_content[enum_body_start:enum_body_end.start()]
    else:
        enum_body = enum_content[enum_body_start:]

    # 提取枚举项
    enum_items = []
    used_values = set()

    proto_enum_pattern = re.compile(
        r'<Global\.ProtoBuf\.ProtoEnum\s*[^>]*Name\s*:=\s*@?"([^"]+)"[^>]*>\s*_\s*'
        r'(\[?\w+\]?)\s*=\s*(\d+)',
        re.IGNORECASE | re.DOTALL
    )

    proto_enum_items = {}

    for item_match in proto_enum_pattern.finditer(enum_content):
        proto_name = item_match.group(1)
        field_name = item_match.group(2).strip('[]')  # 移除方括号转义
        value = int(item_match.group(3))
        proto_enum_items[field_name] = (proto_name, value)

    all_items_pattern = re.compile(
        r'^\s*(\[?\w+\]?)\s*=\s*(\d+)',
        re.MULTILINE | re.IGNORECASE
    )

    for match in all_items_pattern.finditer(enum_body):
        item_name = match.group(1)
        # 移除可能的方括号
        raw_item_name = item_name.strip('[]')
        value = int(match.group(2))

        # 检查是否已处理过这个值
        if value in used_values:
            continue

        # 如果这个项有ProtoEnum注解，使用注解中的名称
        if raw_item_name in proto_enum_items:
            proto_name, proto_value = proto_enum_items[raw_item_name]
            enum_items.append((proto_name, value))
            used_values.add(value)
        else:
            # 否则使用原始名称
            enum_items.append((raw_item_name, value))
            used_values.add(value)

    # 尝试匹配不带值的枚举项
    if not enum_items:
        simple_item_pattern = re.compile(
            r'^\s*(\[?\w+\]?)\s*(?:=\s*(\d+))?\s*$',
            re.MULTILINE | re.IGNORECASE
        )

        next_value = 0
        matches = list(simple_item_pattern.finditer(enum_body))
        for simple_match in matches:
            item_name = simple_match.group(1)
            raw_item_name = item_name.strip('[]')

            if simple_match.group(2):
                value = int(simple_match.group(2))
                next_value = value + 1
            else:
                value = next_value
                next_value += 1

            if value not in used_values:
                used_values.add(value)
                enum_items.append((raw_item_name, value))

    for name, value in enum_items:
        lines.append(f"{indent_str}    {name} = {value};")

    lines.append(f"{indent_str}}}")
    lines.append("")

    return "\n".join(lines)

def extract_top_level_definitions(content):
    definitions = []

    # 查找Namespace的范围
    namespace_match = re.search(r'Namespace\s+\w+', content, re.IGNORECASE)
    namespace_end_match = re.search(r'End\s+Namespace', content, re.IGNORECASE)

    if namespace_match and namespace_end_match:
        namespace_start = namespace_match.end()
        namespace_end = namespace_end_match.start()
        namespace_content = content[namespace_start:namespace_end]
    else:
        namespace_content = content

    # 构建类和枚举的层级结构
    class_boundaries = []

    # 查找所有类边界
    class_pattern = re.compile(r'\bClass\s+(\w+)', re.IGNORECASE)

    # 构建类边界
    for class_match in class_pattern.finditer(namespace_content):
        start = class_match.start()
        class_name = class_match.group(1)
        # 找到对应的End Class
        end_pos = find_matching_end(namespace_content, class_match.end(), 'Class', 'End\\s+Class')
        if end_pos != -1:
            class_boundaries.append((start, end_pos, class_name))

    # 查找所有带ProtoContract的定义
    proto_contract_pattern = re.compile(
        r'<Global\.ProtoBuf\.ProtoContract[^>]*>\s*_',
        re.IGNORECASE | re.DOTALL
    )

    for contract_match in proto_contract_pattern.finditer(namespace_content):
        start_pos = contract_match.start()

        # 查找ProtoContract之后的定义
        rest_content = namespace_content[contract_match.end():]

        # 检查是否为类
        class_match = re.match(r'\s*(?:Partial\s+)?Public\s+Class\s+(\w+)', rest_content, re.IGNORECASE | re.DOTALL)
        if class_match:
            name = class_match.group(1)
            # 检查是否为顶层类
            is_top_level = True
            for class_start, class_end, class_name in class_boundaries:
                if class_start < start_pos < class_end and name != class_name:
                    # 如果当前定义在另一个类内部，则不是顶层
                    is_top_level = False
                    break

            if is_top_level:
                end_pos = find_matching_end(namespace_content, contract_match.end() + class_match.end(), 'Class', 'End\\s+Class')
                if end_pos != -1:
                    definitions.append({
                        'type': 'class',
                        'name': name,
                        'content': namespace_content[start_pos:end_pos],
                        'start': start_pos
                    })
            continue

        # 检查是否为枚举
        enum_match = re.match(r'\s*Public\s+Enum\s+(\w+)', rest_content, re.IGNORECASE | re.DOTALL)
        if enum_match:
            name = enum_match.group(1)
            # 检查是否为顶层枚举
            is_top_level = True
            for class_start, class_end, _ in class_boundaries:
                if class_start < start_pos < class_end:
                    is_top_level = False
                    break

            if is_top_level:
                end_match = re.search(r'End\s+Enum', namespace_content[contract_match.end():], re.IGNORECASE)
                if end_match:
                    end_pos = contract_match.end() + end_match.end()
                    definitions.append({
                        'type': 'enum',
                        'name': name,
                        'content': namespace_content[start_pos:end_pos],
                        'start': start_pos
                    })

    definitions.sort(key=lambda x: x['start'])
    return definitions

def convert_proto(content):
    definitions = extract_top_level_definitions(content)

    lines = ['syntax = "proto3";', ""]

    for defn in definitions:
        if defn['type'] == 'enum':
            enum_content = parse_vb_enum(defn['content'])
            if enum_content:
                lines.append(enum_content)

    for defn in definitions:
        if defn['type'] == 'class':
            class_content = parse_vb_class(defn['content'])
            if class_content:
                lines.append(class_content)

    return "\n".join(lines)

if __name__ == "__main__":
    input_file_path = "D:\\Project\\Code2Protobuf\\input\\pbn_vb\\testDataD.vb"
    output_file_path = "D:\\Project\\Code2Protobuf\\output\\output.proto"

    with open(input_file_path, 'r', encoding='utf-8') as f:
        vbnet_content = f.read()

    proto_content = convert_proto(vbnet_content)

    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write(proto_content)

    print(f"成功生成 {output_file_path}")
