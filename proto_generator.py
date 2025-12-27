from typing import Tuple, Optional
import google.protobuf.descriptor_pb2 as descriptor_pb2

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

def generate_proto_from_bytes(descriptor_bytes: bytes) -> Tuple[str, Optional[str]]:

    file_descriptor = descriptor_pb2.FileDescriptorProto()
    file_descriptor.ParseFromString(descriptor_bytes)

    proto_content = generate_proto_content(file_descriptor)

    # name
    proto_filename = file_descriptor.name
    if proto_filename:
        proto_filename = proto_filename
    else:
        proto_filename = None

    return proto_content, proto_filename
