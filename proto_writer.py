from pathlib import Path
import re
from proto_generator import generate_proto_from_bytes
from google.protobuf.descriptor_pb2 import FileDescriptorSet, FileDescriptorProto

def get_proto_file_name(source_code, file_descriptor, source_language):
    if file_descriptor.name:
        return Path(file_descriptor.name).name

    name = None
    if source_language == 'csharp':
        name = get_csharp_proto_name(source_code)
    elif source_language == 'java':
        name = get_java_proto_name(source_code)
    elif source_language == 'go':
        name = get_go_proto_name(source_code)
    elif source_language == 'python':
        name = get_python_proto_name(source_code)
    elif source_language == 'ruby':
        name = get_ruby_proto_name(source_code)
    elif source_language == 'php':
        name = get_php_proto_name(source_code)
    elif source_language == 'cpp':
        name = get_cpp_proto_name(source_code)

    if name:
        return name

    raise ValueError(
        "Cannot determine proto filename: Missing FileDescriptorProto.name and "
        "no recognizable pattern in source code"
    )

def get_csharp_proto_name(csharp_code):
    source_match = re.search(r'^//\s*source:\s*(.+?\.proto)\s*$', csharp_code, re.MULTILINE)
    if source_match:
        return Path(source_match.group(1)).name

    pattern = re.compile(r'public\s+static\s+partial\s+class\s+(\w+)Reflection\b')
    match = pattern.search(csharp_code)
    if match:
        return f"{match.group(1)}.proto"

    return None

def get_java_proto_name(java_code):
    class_pattern = r"public\s+final\s+class\s+(\w+)(?:OuterClass)?\s*\{"
    match = re.search(class_pattern, java_code)
    if match:
        class_name = match.group(1)
        if class_name.endswith("OuterClass"):
            class_name = class_name[:-len("OuterClass")]
        return f"{class_name}.proto"
    return None

def get_go_proto_name(go_code):
    source_match = re.search(r'^//\s*source:\s*(.+?\.proto)\s*$', go_code, re.MULTILINE)
    if source_match:
        return Path(source_match.group(1)).name

    pattern = re.compile(r'var\s+file_(\w+)_proto_rawDesc')
    match = pattern.search(go_code)
    if match:
        return f"{match.group(1)}.proto"

    return None

def get_python_proto_name(python_code):
    source_match = re.search(r'^#\s*source:\s*(.+?\.proto)\s*$', python_code, re.MULTILINE)
    if source_match:
        return Path(source_match.group(1)).name
    return None

def get_ruby_proto_name(ruby_code):
    source_match = re.search(r'^#\s*source:\s*(.+?\.proto)\s*$', ruby_code, re.MULTILINE)
    if source_match:
        return Path(source_match.group(1)).name
    return None

def get_php_proto_name(php_code):
    source_match = re.search(r'^#\s*source:\s*(.+?\.proto)\s*$', php_code, re.MULTILINE)
    if source_match:
        return Path(source_match.group(1)).name

    class_match = re.search(r'class\s+(\w+)\s*\{', php_code)
    if class_match:
        return f"{class_match.group(1)}.proto"

    return None

def get_cpp_proto_name(cpp_code):
    source_match = re.search(r'^//\s*source:\s*(.+?\.proto)\s*$', cpp_code)
    if source_match:
        return Path(source_match.group(1)).name

    pattern = re.compile(
        r'const\s+char\s+descriptor_table_protodef_(\w+)\[\]',
        re.DOTALL
    )
    match = pattern.search(cpp_code)
    if match:
        file_name = match.group(1)
        file_name = file_name.replace('_2e', '.')
        file_name = file_name.replace('_5f', '_')
        return file_name

    return None

def generate_proto_file(descriptor_data, output_directory, source_code, source_language):
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    generated_files = []

    if source_language == 'php':
        file_set = FileDescriptorSet()
        file_set.ParseFromString(descriptor_data)

        for file_proto in file_set.file:
            proto_content, proto_name_from_descriptor = generate_proto_from_bytes(file_proto.SerializeToString())

            if proto_name_from_descriptor is not None:
                proto_file_name = proto_name_from_descriptor
            else:
                proto_file_name = get_proto_file_name(source_code, file_proto, source_language)

            output_file = output_path / proto_file_name

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(proto_content)

            print(f"Generated: {output_file}")
            generated_files.append(str(output_file))

    else:
        file_descriptor = FileDescriptorProto()
        file_descriptor.ParseFromString(descriptor_data)

        proto_content, proto_name_from_descriptor = generate_proto_from_bytes(descriptor_data)

        if proto_name_from_descriptor is not None:
            proto_file_name = proto_name_from_descriptor
        else:
            proto_file_name = get_proto_file_name(source_code, file_descriptor, source_language)

        output_file = output_path / proto_file_name

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(proto_content)

        print(f"Generated: {output_file}")
        generated_files.append(str(output_file))

    return generated_files
