import sys
import argparse
import binascii
import base64
import re
from pathlib import Path
import google.protobuf.descriptor_pb2 as descriptor_pb2

def extract_from_csharp(csharp_code):
    pattern = re.compile(
        r'descriptorData\s*=\s*global::System\.Convert\.FromBase64String\s*\(\s*string\.Concat\s*\(([\s\S]*?)\)\s*\);',
        re.DOTALL
    )
    match = pattern.search(csharp_code)
    
    if match:
        concat_arguments = match.group(1)
        string_matches = re.findall(r'"([^"]*)"', concat_arguments)
        
        if not string_matches:
            print("No string fragments found in string.Concat")
            return None

        full_base64 = ''.join(string_matches)
        try:
            return base64.b64decode(full_base64)
        except binascii.Error as e:
            print(f"Error decoding Base64 string: {str(e)}")
            return None

    pattern = re.compile(
        r'byte\[]\s+descriptorData\s*=\s*global::System\.Convert\.FromBase64String\s*\(\s*@?"([^"]+)"\s*\);',
        re.DOTALL
    )
    match = pattern.search(csharp_code)
    
    if match:
        base64_str = match.group(1)
        try:
            return base64.b64decode(base64_str)
        except binascii.Error as e:
            print(f"Error decoding Base64 string: {str(e)}")
            return None

    print("DescriptorData assignment not found in C# code")
    return None

def generate_proto_file(descriptor_data, output_directory, source_code):
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    file_descriptor = descriptor_pb2.FileDescriptorProto()
    file_descriptor.ParseFromString(descriptor_data)

    proto_file_name = get_proto_file_name(source_code, file_descriptor)
    output_file = output_path / proto_file_name

    proto_content = generate_proto_content(file_descriptor)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(proto_content)

    print(f"Generated: {output_file}")

def get_proto_file_name(source_code, file_descriptor):
    if file_descriptor.name:
        return Path(file_descriptor.name).name
    
    reflection_match = re.search(r'public\s+static\s+partial\s+class\s+(\w+)Reflection\b', source_code)
    if reflection_match:
        return f"{reflection_match.group(1)}.proto"

    source_match = re.search(r'source:\s*"([^"]+)"', source_code)
    if source_match:
        return Path(source_match.group(1)).name

    raise ValueError("Cannot determine proto filename from C# source")

def generate_proto_content(file_descriptor):
    lines = []

    syntax = file_descriptor.syntax if file_descriptor.syntax else "proto3"
    lines.append(f'syntax = "{syntax}";\n')

    if file_descriptor.package:
        lines.append(f"package {file_descriptor.package};\n")

    for dependency in file_descriptor.dependency:
        lines.append(f'import "{dependency}";')

    if file_descriptor.dependency:
        lines.append("")

    for enum in file_descriptor.enum_type:
        generate_enum(enum, lines, 0)

    for message in file_descriptor.message_type:
        generate_message(message, lines, 0)

    return "\n".join(lines)

def generate_enum(enum_desc, lines, indent_level):
    indent = "    " * indent_level
    lines.append(f"{indent}enum {get_simple_type_name(enum_desc.name)} {{")
    for value in enum_desc.value:
        lines.append(f"{indent}    {value.name} = {value.number};")
    lines.append(f"{indent}}}")
    lines.append("")

def generate_message(message_desc, lines, indent_level):
    indent = "    " * indent_level
    lines.append(f"{indent}message {get_simple_type_name(message_desc.name)} {{")

    generate_map_fields(message_desc, lines, indent_level)

    for field in message_desc.field:
        if field.HasField("oneof_index"):
            continue

        if is_map_field(field, message_desc):
            continue

        field_label = get_field_label(field)
        field_type = get_field_type(field)
        lines.append(f"{indent}    {field_label}{field_type} {field.name} = {field.number};")

    generate_oneof_fields(message_desc, lines, indent_level)

    generate_nested_types(message_desc, lines, indent_level)

    lines.append(f"{indent}}}")
    lines.append("")

def generate_map_fields(message_desc, lines, indent_level):
    indent = "    " * indent_level
    for nested in message_desc.nested_type:
        if nested.options.map_entry:
            map_field = find_map_field(nested, message_desc)
            if map_field:
                key_field, value_field = get_map_entry_fields(nested)
                key_type = get_field_type(key_field)
                value_type = get_field_type(value_field)
                lines.append(f"{indent}    map<{key_type}, {value_type}> {map_field.name} = {map_field.number};")

def is_map_field(field, message_desc):
    for nested in message_desc.nested_type:
        if nested.options.map_entry:
            if field.type_name.endswith(nested.name):
                return True
    return False

def generate_oneof_fields(message_desc, lines, indent_level):
    if not message_desc.oneof_decl:
        return

    indent = "    " * indent_level
    oneof_groups = group_oneof_fields(message_desc)

    for index, fields in oneof_groups.items():
        if index >= len(message_desc.oneof_decl):
            continue

        oneof_name = message_desc.oneof_decl[index].name
        lines.append(f"{indent}    oneof {oneof_name} {{")
        for field in fields:
            field_type = get_field_type(field)
            lines.append(f"{indent}        {field_type} {field.name} = {field.number};")
        lines.append(f"{indent}    }}")

def generate_nested_types(message_desc, lines, indent_level):
    for enum in message_desc.enum_type:
        generate_enum(enum, lines, indent_level + 1)
    for nested in message_desc.nested_type:
        if not nested.options.map_entry:
            generate_message(nested, lines, indent_level + 1)

def find_map_field(map_entry, parent_desc):
    for field in parent_desc.field:
        if field.type_name.endswith(map_entry.name):
            return field
    return None

def get_map_entry_fields(map_entry):
    return map_entry.field[0], map_entry.field[1]

def group_oneof_fields(message_desc):
    oneof_groups = {}
    for field in message_desc.field:
        if field.HasField("oneof_index"):
            index = field.oneof_index
            oneof_groups.setdefault(index, []).append(field)
    
    return oneof_groups

def get_field_label(field):
    if field.label == field.LABEL_REPEATED:
        return "repeated "
    if field.proto3_optional:
        return "optional "
    return ""

def get_field_type(field):
    if field.HasField("type_name"):
        return get_simple_type_name(field.type_name)

    type_mapping = {
        field.TYPE_DOUBLE: "double",
        field.TYPE_FLOAT: "float",
        field.TYPE_INT64: "int64",
        field.TYPE_UINT64: "uint64",
        field.TYPE_INT32: "int32",
        field.TYPE_FIXED64: "fixed64",
        field.TYPE_FIXED32: "fixed32",
        field.TYPE_BOOL: "bool",
        field.TYPE_STRING: "string",
        field.TYPE_BYTES: "bytes",
        field.TYPE_UINT32: "uint32",
        field.TYPE_SFIXED32: "sfixed32",
        field.TYPE_SFIXED64: "sfixed64",
        field.TYPE_SINT32: "sint32",
        field.TYPE_SINT64: "sint64",
    }
    return type_mapping.get(field.type, "unknown")

def get_simple_type_name(full_name):
    if full_name.startswith("."):
        full_name = full_name[1:]
    return full_name.split(".")[-1]

def unquote_argument(arg):
    if arg.startswith('"') and arg.endswith('"'):
        return arg[1:-1]
    return arg

def print_usage():
    print("Usage:")
    print("  --input, -i     Input file or directory path.")
    print("  --output, -o    Output directory path.")
    print("  --help, -h      Display this help message.")

if __name__ == "__main__":
    input_path = None
    output_dir = None

    if input_path is None or output_dir is None:
        parser = argparse.ArgumentParser(add_help=False)

        parser.add_argument(
            "-i", "--input",
            dest="input_path",
            required=False,
        )
        parser.add_argument(
            "-o", "--output",
            dest="output_directory",
            required=False,
        )
        parser.add_argument(
            "-h", "--help",
            action="store_true",
            dest="show_help",
        )

        args, unknown = parser.parse_known_args()

        if args.show_help:
            print_usage()
            sys.exit(0)

        if args.input_path and args.output_directory:
            if input_path is None:
                input_path = Path(unquote_argument(args.input_path))
            if output_dir is None:
                output_dir = Path(unquote_argument(args.output_directory))

    else:
        input_path = Path(input_path)
        output_dir = Path(output_dir)

    if input_path is None or output_dir is None:
        print("Error: The input and output paths must be specified.", file=sys.stderr)
        print_usage()
        sys.exit(1)

    if not input_path.exists():
        print(f"Error: Input path not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        if input_path.is_file():
            with open(input_path, "r", encoding="utf-8") as f:
                source_code = f.read()

            descriptor_data = extract_from_csharp(source_code)

            if not descriptor_data:
                raise ValueError("DescriptorData not found in source code")

            generate_proto_file(descriptor_data, output_dir, source_code)

        elif input_path.is_dir():
            file_pattern = "*.cs"
            source_files = list(input_path.rglob(file_pattern))

            if not source_files:
                print(f"No {file_pattern} files found in {input_path}")
                sys.exit()

            for file_path in source_files:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        source_code = f.read()

                    descriptor_data = extract_from_csharp(source_code)
                    if not descriptor_data:
                        print(f"Warning: DescriptorData not found in {file_path}. Skipping.")
                        continue

                    generate_proto_file(descriptor_data, output_dir, source_code)

                except Exception as e:
                    print(f"Error processing file {file_path}: {str(e)}", file=sys.stderr)

        else:
            print(f"Error: Input path is neither file nor directory: {input_path}", file=sys.stderr)
            sys.exit(1)

    except Exception as ex:
        print(f"Error: {str(ex)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
