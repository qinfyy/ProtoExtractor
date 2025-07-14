import re
import os
import sys

def extract_enums(rust_code):
    enums = []
    enum_pattern = r'pub\s+enum\s+(\w+)\s*\{([^}]*?)\}'

    for match in re.finditer(enum_pattern, rust_code, re.DOTALL):
        enum_name = match.group(1)
        variants_block = match.group(2)

        variants = []
        for var_match in re.finditer(r'(\w+)\s*=\s*(\d+)', variants_block):
            variant_name, value = var_match.groups()
            variants.append(f"{variant_name} = {value}")

        if variants:
            enum_def = f"enum {enum_name} {{\n" + "\n".join([f"\t{v};" for v in variants]) + "\n}"
            enums.append(enum_def)

    return enums

def extract_prost_attributes(field_block):
    prost_match = re.search(r'#\[prost\(([\s\S]*?)\)\]', field_block, re.DOTALL)
    if not prost_match:
        return None

    prost_str = prost_match.group(1).replace('\n', ' ')
    attributes = {}

    type_match = re.search(r'([a-z]+[0-9]*|message|enumeration|bytes|string|bool|float|double)', prost_str)
    if type_match:
        attributes['type'] = type_match.group(1)

    tag_match = re.search(r'tag\s*=\s*"(\d+)"', prost_str)
    if tag_match:
        attributes['tag'] = tag_match.group(1)

    if 'repeated' in prost_str:
        attributes['rule'] = 'repeated'
    elif 'optional' in prost_str:
        attributes['rule'] = 'optional'
    elif 'map' in prost_str:
        attributes['rule'] = 'map'
    elif 'oneof' in prost_str:
        attributes['rule'] = 'oneof'

    if attributes.get('rule') == 'map':
        map_match = re.search(r'map\s*=\s*"([^"]+)"', prost_str)
        if map_match:
            parts = map_match.group(1).split(',', 1)
            if len(parts) == 2:
                key_type = parts[0].strip()
                value_type = parts[1].strip()

                if 'enumeration' in value_type:
                    enum_match = re.search(r'enumeration\s*\(\s*([\w:]+)\s*\)', value_type)
                    if enum_match:
                        full_name = enum_match.group(1)
                        value_type = full_name.split(':')[-1]

                attributes['map_key'] = key_type
                attributes['map_value'] = value_type

    if 'enumeration' in prost_str:
        enum_match = re.search(r'enumeration\s*\(\s*"?([\w:]+)"?\s*\)', prost_str)
        if not enum_match:
            enum_match = re.search(r'enumeration\s*[=\s]*"([\w:]+)"', prost_str)

        if enum_match:
            full_name = enum_match.group(1)
            attributes['enum_type'] = full_name.split(':')[-1]

    if attributes.get('rule') == 'oneof':
        oneof_match = re.search(r'oneof\s*=\s*"([\w:]+)"', prost_str)
        if oneof_match:
            attributes['oneof_name'] = oneof_match.group(1).split(':')[-1]
        tags_match = re.search(r'tags\s*=\s*"([\d,]+)"', prost_str)
        if tags_match:
            attributes['oneof_tags'] = tags_match.group(1)

    return attributes

def extract_hashmap_value_type(field_block):
    pattern = r'::std::collections::HashMap<[^,]+,\s*([^>\n]+)\s*>'
    match = re.search(pattern, field_block, re.DOTALL)
    if match:
        value_type = match.group(1).strip()
        if '::' in value_type:
            return value_type.split('::')[-1]
        return value_type
    return None

def extract_message_type(field_block):
    path_pattern = r'[:\s]+((?:[a-zA-Z0-9_]+::)*)([A-Z][a-zA-Z0-9_]+)\s*,'
    path_match = re.search(path_pattern, field_block, re.DOTALL)
    if path_match:
        return path_match.group(2)

    container_pattern = r'Vec<\s*((?:[a-zA-Z0-9_]+::)*)([A-Z][a-zA-Z0-9_]+)\s*>'
    container_match = re.search(container_pattern, field_block, re.DOTALL)
    if container_match:
        return container_match.group(2)

    option_pattern = r'Option<\s*((?:[a-zA-Z0-9_]+::)*)([A-Z][a-zA-Z0-9_]+)\s*>'
    option_match = re.search(option_pattern, field_block, re.DOTALL)
    if option_match:
        return option_match.group(2)

    nested_pattern = r'::(?:[a-zA-Z0-9_]+::)+[a-zA-Z0-9_]+<\s*((?:[a-zA-Z0-9_]+::)*)([A-Z][a-zA-Z0-9_]+)\s*>'
    nested_match = re.search(nested_pattern, field_block, re.DOTALL)
    if nested_match:
        return nested_match.group(2)

    absolute_path_pattern = r'::((?:[a-zA-Z0-9_]+::)*)([A-Z][a-zA-Z0-9_]+)\s*,'
    absolute_match = re.search(absolute_path_pattern, field_block, re.DOTALL)
    if absolute_match:
        return absolute_match.group(2)

    generic_pattern = r'[A-Z][a-zA-Z0-9_]+<\s*((?:[a-zA-Z0-9_]+::)*)([A-Z][a-zA-Z0-9_]+)\s*>'
    generic_match = re.search(generic_pattern, field_block, re.DOTALL)
    if generic_match:
        return generic_match.group(2)

    name_match = re.search(r'[:\s]+([A-Z][a-zA-Z0-9_]+)\s*,', field_block, re.DOTALL)
    if name_match:
        return name_match.group(1)

    candidates = re.findall(r'([A-Z][a-zA-Z0-9_]+)', field_block)
    if candidates:
        common_types = {"String", "Vec", "Option", "HashMap", "Box", "Result"}
        for candidate in reversed(candidates):
            if candidate not in common_types:
                return candidate

    return "unknown"

def extract_field_type(field_block, prost_attrs, all_messages, all_enums):
    if prost_attrs.get('enum_type'):
        enum_name = prost_attrs['enum_type']
        if any(f"enum {enum_name}" in e for e in all_enums):
            return enum_name

        for enum_def in all_enums:
            enum_match = re.search(r'enum\s+(\w+)', enum_def)
            if enum_match and enum_match.group(1) == enum_name:
                return enum_name
        return "int32"

    if prost_attrs.get('type') == 'message':
        message_type = extract_message_type(field_block)

        if message_type == "unknown":
            type_match = re.search(r'::core::option::Option<([\w:]+)>', field_block)
            if type_match:
                full_type = type_match.group(1)
                if '::' in full_type:
                    return full_type.split('::')[-1]
                return full_type

            name_match = re.search(r'pub\s+(\w+)\s*:', field_block)
            if name_match:
                field_name = name_match.group(1)
                for msg in all_messages:
                    if re.search(r'message\s+' + field_name, msg):
                        return field_name

        return message_type

    type_mapping = {
        'int32': 'int32',
        'uint32': 'uint32',
        'int64': 'int64',
        'uint64': 'uint64',
        'sint32': 'sint32',
        'sint64': 'sint64',
        'fixed32': 'fixed32',
        'fixed64': 'fixed64',
        'sfixed32': 'sfixed32',
        'sfixed64': 'sfixed64',
        'float': 'float',
        'double': 'double',
        'string': 'string',
        'bool': 'bool',
        'bytes': 'bytes',
        'enumeration': 'int32',
    }

    prost_type = prost_attrs.get('type', '')

    if prost_type in type_mapping:
        return type_mapping[prost_type]

    return "unknown"

def extract_field_blocks(fields_block):
    field_blocks = []
    lines = fields_block.split('\n')
    current_block = None
    bracket_depth = 0
    brace_depth = 0

    for line in lines:
        brace_depth += line.count('{') - line.count('}')
        bracket_depth += line.count('<') - line.count('>')

        if re.search(r'#\[prost\(', line):
            if current_block is not None:
                field_blocks.append(current_block.strip())

            current_block = line
        elif current_block is not None:
            current_block += '\n' + line
            if (',' in line or ';' in line) and bracket_depth == 0 and brace_depth == 0:
                field_blocks.append(current_block.strip())
                current_block = None

    if current_block is not None:
        field_blocks.append(current_block.strip())

    return field_blocks

def find_oneof_definition(rust_code, oneof_name, current_position):
    oneof_pattern = rf'#\[derive\([^\]]*::prost::Oneof[^\]]*\)\][\s\S]*?pub\s+enum\s+{oneof_name}\s*\{{([^}}]*?)\}}'
    oneof_match = re.search(oneof_pattern, rust_code[current_position:], re.DOTALL)
    if oneof_match:
        variants_block = oneof_match.group(1)
        return oneof_match.start() + current_position, variants_block

    oneof_match = re.search(oneof_pattern, rust_code, re.DOTALL)
    if oneof_match:
        variants_block = oneof_match.group(1)
        return oneof_match.start(), variants_block

    return None, None

def extract_last_part_of_type(type_str):
    if '::' in type_str:
        return type_str.split('::')[-1]
    return type_str

def extract_oneof_variants(variants_block):
    variants = []
    variant_matches = re.finditer(
        r'#\[prost\(([^)]*)\)\]\s*(\w+)\s*(?:\(\s*([^)]*)\s*\))?',
        variants_block
    )

    for var_match in variant_matches:
        prost_attrs_part = var_match.group(1)
        variant_name = var_match.group(2)
        type_info = var_match.group(3) or ''

        tag = "0"
        tag_match = re.search(r'tag\s*=\s*"(\d+)"', prost_attrs_part)
        if tag_match:
            tag = tag_match.group(1)
        else:
            tags_match = re.search(r'tags\s*=\s*"([\d,]+)"', prost_attrs_part)
            if tags_match:
                tags = tags_match.group(1).split(',')
                tag = tags[len(variants)] if len(variants) < len(tags) else "0"

        field_type = None
        enum_match = re.search(r'enumeration\s*=\s*"?([\w:]+)"?', prost_attrs_part)

        if enum_match:
            full_enum_name = enum_match.group(1)
            field_type = extract_last_part_of_type(full_enum_name)

        if not field_type:
            msg_match = re.search(r'message\s*=\s*"([\w:]+)"', prost_attrs_part)
            if msg_match:
                full_msg_name = msg_match.group(1)
                field_type = extract_last_part_of_type(full_msg_name)

        if not field_type:
            type_mapping = {
                'int32': 'int32',
                'uint32': 'uint32',
                'int64': 'int64',
                'uint64': 'uint64',
                'sint32': 'sint32',
                'sint64': 'sint64',
                'fixed32': 'fixed32',
                'fixed64': 'fixed64',
                'sfixed32': 'sfixed32',
                'sfixed64': 'sfixed64',
                'float': 'float',
                'double': 'double',
                'string': 'string',
                'bool': 'bool',
                'bytes': 'bytes'
            }

            for t in type_mapping:
                if re.search(rf'\b{t}\b', prost_attrs_part):
                    field_type = type_mapping[t]
                    break

        if not field_type and type_info:
            clean_type = extract_last_part_of_type(type_info)
            if clean_type in ['i32', 'u32', 'i64', 'u64', 'f32', 'f64', 'bool', 'String', 'Vec<u8>']:
                rust_to_proto = {
                    'i32': 'int32',
                    'u32': 'uint32',
                    'i64': 'int64',
                    'u64': 'uint64',
                    'f32': 'float',
                    'f64': 'double',
                    'bool': 'bool',
                    'String': 'string',
                    'Vec<u8>': 'bytes'
                }
                field_type = rust_to_proto.get(clean_type, clean_type)
            else:
                field_type = clean_type

        if not field_type:
            field_type = "unknown"

        variants.append(f"\t\t{field_type} {variant_name} = {tag};")

    return variants

def extract_structs(rust_code, all_messages, all_enums):
    structs = []
    struct_pattern = r'pub\s+struct\s+(\w+)\s*\{([^}]*?)\}'
    processed_oneofs = set()

    for match in re.finditer(struct_pattern, rust_code, re.DOTALL):
        struct_name = match.group(1)
        end_pos = match.end()

        fields_block = match.group(2)

        field_blocks = extract_field_blocks(fields_block)

        fields = []

        for field_block in field_blocks:
            prost_attrs = extract_prost_attributes(field_block)
            if not prost_attrs:
                continue

            field_name_match = re.search(r'pub\s+(?:r#)?(\w+)\s*:', field_block)
            if not field_name_match:
                continue
            field_name = field_name_match.group(1)

            tag = prost_attrs.get('tag', '0')

            if prost_attrs.get('rule') == 'oneof':
                oneof_name = prost_attrs.get('oneof_name', '').split('::')[-1] or "MyOneof"

                oneof_key = f"{struct_name}::{oneof_name}"
                if oneof_key in processed_oneofs:
                    continue

                oneof_pos, variants_block = find_oneof_definition(rust_code, oneof_name, end_pos)
                if variants_block:
                    variants = extract_oneof_variants(variants_block)
                    if variants:
                        oneof_def = f"\toneof {oneof_name} {{\n" + "\n".join(variants) + "\n\t}"
                        fields.append(oneof_def)
                        processed_oneofs.add(oneof_key)
                        continue
                else:
                    print(f"Warning: The oneof definition {oneof_name} was not found in the struct {struct_name}.")

                processed_oneofs.add(oneof_key)
                continue

            if prost_attrs.get('rule') == 'map':
                if 'map_key' in prost_attrs and 'map_value' in prost_attrs:
                    key_type = prost_attrs['map_key']
                    value_type = prost_attrs['map_value']

                    if value_type == 'message':
                        value_type = extract_hashmap_value_type(field_block)
                        if not value_type:
                            value_type = "unknown_message"
                    elif value_type == 'enumeration':
                        value_type = prost_attrs.get('enum_type', 'enumeration')

                    value_type = value_type.rstrip(',')

                    fields.append(f"\tmap<{key_type}, {value_type}> {field_name} = {tag};")
                else:
                    print(f"Warning: The mapping information for the field {field_name} in the struct {struct_name} is incomplete.")
                    fields.append(f"\tmap<unknown, unknown> {field_name} = {tag};")
                continue

            field_type = extract_field_type(field_block, prost_attrs, all_messages, all_enums)

            rule = prost_attrs.get('rule', '')

            if rule == 'repeated':
                field_def = f"\trepeated {field_type} {field_name} = {tag};"
            elif rule == 'optional':
                field_def = f"\toptional {field_type} {field_name} = {tag};"
            else:
                field_def = f"\t{field_type} {field_name} = {tag};"

            fields.append(field_def)

        struct_def = f"message {struct_name} {{\n" + "\n".join(fields) + "\n}"
        structs.append(struct_def)

    return structs

def extract_nested_modules(rust_code, all_messages, all_enums):
    nested_defs = []
    mod_pattern = r'pub\s+mod\s+(\w+)\s*\{([^}]*?)\}'

    for mod_match in re.finditer(mod_pattern, rust_code, re.DOTALL):
        mod_block = mod_match.group(2)

        structs = extract_structs(mod_block, all_messages, all_enums)
        nested_defs.extend(structs)

    return nested_defs

def convert_rust_to_proto(rust_code):
    rust_code = re.sub(r'//.*', '', rust_code)
    rust_code = re.sub(r'/\*.*?\*/', '', rust_code, flags=re.DOTALL)
    rust_code = re.sub(r'impl\s+[\w:]+\s*\{[^}]*\}', '', rust_code, flags=re.DOTALL)

    rust_code = re.sub(r'#\[\s*prost\s*\(', '#[prost(', rust_code)

    enums = extract_enums(rust_code)

    all_messages = []

    main_structs = extract_structs(rust_code, all_messages, enums)
    all_messages.extend(main_structs)

    nested_defs = extract_nested_modules(rust_code, all_messages, enums)
    all_messages.extend(nested_defs)

    new_structs = extract_structs(rust_code, all_messages, enums)
    all_messages = new_structs + nested_defs

    message_names = set()
    for msg in all_messages:
        name_match = re.search(r'message\s+(\w+)', msg)
        if name_match:
            message_names.add(name_match.group(1))

    proto_code = 'syntax = "proto3";\n\n'

    unique_messages = []
    seen_messages = set()
    for msg in all_messages:
        name_match = re.search(r'message\s+(\w+)', msg)
        if name_match:
            msg_name = name_match.group(1)
            if msg_name not in seen_messages:
                unique_messages.append(msg)
                seen_messages.add(msg_name)

    if unique_messages:
        proto_code += "\n\n".join(unique_messages) + "\n\n"

    unique_enums = []
    seen_enums = set()
    for enum in enums:
        name_match = re.search(r'enum\s+(\w+)', enum)
        if name_match:
            enum_name = name_match.group(1)
            if enum_name not in seen_enums:
                unique_enums.append(enum)
                seen_enums.add(enum_name)

    if unique_enums:
        proto_code += "\n\n".join(unique_enums) + "\n"

    return proto_code

if __name__ == "__main__":
    input_file = "testDataC_pb.rs"
    output_file = "output.proto"

    if not os.path.exists(input_file):
        print(f"Error: The input file {input_file} was not found")
        sys.exit()

    with open(input_file, 'r', encoding='utf-8') as f:
        rust_code = f.read()

    proto_code = convert_rust_to_proto(rust_code)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(proto_code)

    print(f"{input_file} has been converted to {output_file}")
