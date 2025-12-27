import re
import binascii
import base64

def extract_descriptor_data(source_code, source_language):
    if source_language == 'csharp':
        return extract_from_csharp(source_code)
    elif source_language == 'java':
        return extract_from_java(source_code)
    elif source_language == 'go':
        return extract_from_go(source_code)
    elif source_language == 'python':
        return extract_from_python(source_code)
    elif source_language == 'ruby':
        return extract_from_ruby(source_code)
    elif source_language == 'php':
        return extract_from_php(source_code)
    elif source_language == 'cpp':
        return extract_from_cpp(source_code)
    else:
        raise ValueError(f"Unsupported source language: {source_language}")

def extract_from_csharp(csharp_code):
    # descriptorData = global::System.Convert.FromBase64String(string.Concat(...));
    pattern = re.compile(
        r'descriptorData\s*=\s*global::System\.Convert\.FromBase64String\s*\(\s*string\.Concat\s*\(([\s\S]*?)\)\s*\);',
        re.DOTALL
    )

    match = pattern.search(csharp_code)
    if not match:
        # byte[] descriptorData = global::System.Convert.FromBase64String(@"...");
        pattern = re.compile(
            r'byte\[]\s+descriptorData\s*=\s*global::System\.Convert\.FromBase64String\s*\(\s*@?"([^"]+)"\s*\);',
            re.DOTALL
        )
        match = pattern.search(csharp_code)
        if match:
            base64_str = match.group(1)
            return base64.b64decode(base64_str)
        else:
            print("DescriptorData assignment not found in C# code")
            return None

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

def extract_from_java(java_code):
    array_pattern = re.compile(
        r"static\s*\{\s*"
        r"java\.lang\.String\[]\s+descriptorData\s*=\s*\{\s*"
        r"([\s\S]*?)\s*}\s*;",
        re.DOTALL
    )

    array_match = array_pattern.search(java_code)
    if not array_match:
        print("DescriptorData array not found in static block")
        return None

    array_content = array_match.group(1)
    full_string = ""

    string_pattern = re.compile(r'"((?:\\.|[^"\\])*)"')
    for match in string_pattern.finditer(array_content):
        escaped_string = match.group(1)
        full_string += escaped_string

    raw_bytes = process_escape_sequences(full_string).encode("latin-1")
    return raw_bytes

def extract_from_go(go_code: str) -> bytes | None:
    # 新版本
    # const file_testDataC_proto_rawDesc = "..." + "..."
    const_match = re.search(r'const\s+file_\w+_proto_rawDesc\s*=', go_code)
    if const_match:
        start_idx = const_match.end()
        remaining_code = go_code[start_idx:]

        # 匹配连续的字符串字面量，允许中间有 +、空格、换行
        string_parts = re.findall(r'"((?:\\.|[^"\\])*)"', remaining_code)
        if string_parts:
            full_escaped = ''.join(string_parts)
            try:
                # cnmd go lang, cnmd protobuf-go
                return process_go_escape_sequences(full_escaped)
            except ValueError as e:
                print(f"Error decoding Go escape sequences: {e}")
                return None

    # 旧版本
    # var file_filename_proto_rawDesc = []byte{...}
    # var file_filename_proto_rawDesc = string([]byte{...})
    pattern = re.compile(
        r'var\s+file_\w+_proto_rawDesc\s*=\s*(?:string\s*\()?\s*\[\]byte\s*\{([\s\S]+?)\}(?:\s*\))?',
        re.DOTALL
    )
    match = pattern.search(go_code)
    if match:
        byte_array_content = match.group(1)
        try:
            return parse_go_byte_array(byte_array_content)
        except ValueError as e:
            print(f"Error parsing Go byte array: {e}")
            return None

    print("Raw descriptor not found in Go code")
    return None

def extract_from_python(python_code):
    # DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'...')
    pattern = re.compile(
        r'DESCRIPTOR\s*=\s*_descriptor_pool\.Default\(\)\.AddSerializedFile\(b([\'"])(.*?)\1\)',
        re.DOTALL
    )

    match = pattern.search(python_code)
    if not match:
        # DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile('...')
        pattern = re.compile(
            r'DESCRIPTOR\s*=\s*_descriptor_pool\.Default\(\)\.AddSerializedFile\(([\'"])(.*?)\1\)',
            re.DOTALL
        )
        match = pattern.search(python_code)
        if not match:
            print("DESCRIPTOR assignment with AddSerializedFile not found")
            return None

    byte_str = match.group(2)

    processed_bytes = process_escape_sequences(byte_str).encode("latin-1")
    return processed_bytes

def extract_from_ruby(ruby_code):
    # descriptor_data = "..."
    pattern = re.compile(
        r'descriptor_data\s*=\s*"((?:\\"|[^"])*)"',
        re.DOTALL
    )

    match = pattern.search(ruby_code)
    if match:
        escaped_string = match.group(1)
        processed_bytes = process_escape_sequences(escaped_string).encode("latin-1")
        return processed_bytes

    # pool.add_serialized_file(descriptor_data)
    pool_match = re.search(
        r'pool\.add_serialized_file\(descriptor_data\)',
        ruby_code
    )
    if pool_match:
        assignment_pattern = re.compile(
            r'(descriptor_data\s*=\s*[\s\S]+?)\n\s*pool\.add_serialized_file',
            re.DOTALL
        )
        assignment_match = assignment_pattern.search(ruby_code)
        if assignment_match:
            assignment_line = assignment_match.group(1)
            string_match = re.search(r'"((?:\\"|[^"])*)"', assignment_line)
            if string_match:
                escaped_string = string_match.group(1)
                return process_escape_sequences(escaped_string).encode("latin-1")

    print("descriptor_data assignment not found in Ruby code")
    return None

def extract_from_php(php_code):
    # $pool->internalAddGeneratedFile(...)
    pattern = re.compile(
        r'\$pool->internalAddGeneratedFile\s*\(\s*"((?:\\"|[^"])*)"\s*,\s*true\s*\)',
        re.DOTALL
    )

    match = pattern.search(php_code)
    if not match:
        print("internalAddGeneratedFile call not found in PHP code")
        return None

    escaped_string = match.group(1)
    processed_bytes = process_escape_sequences(escaped_string).encode("latin-1")
    return processed_bytes

def extract_from_cpp(cpp_code):
    pattern = re.compile(
        r'const\s+char\s+descriptor_table_protodef_\w+\[]\s*ABSL_ATTRIBUTE_SECTION_VARIABLE\(\s*protodesc_cold\s*\)\s*=\s*{\s*([\s\S]+?)\s*}\s*;',
        re.DOTALL
    )

    match = pattern.search(cpp_code)
    if not match:
        pattern = re.compile(
            r'const\s+char\s+descriptor_table_protodef_\w+\[]\s*=\s*{\s*([\s\S]+?)\s*}\s*;',
            re.DOTALL
        )
        match = pattern.search(cpp_code)
        if not match:
            print("Descriptor table not found in C++ code")
            return None

    array_content = match.group(1)
    full_bytes = bytearray()

    char_pattern = re.compile(
        r"'("
        r"(?:"
        r"\\['\"\\?abfnrtv]|"
        r"\\[0-7]{1,3}|"
        r"\\x[0-9a-fA-F]{2}|"
        r"\\u[0-9a-fA-F]{4}|"
        r"\\U[0-9a-fA-F]{8}|"
        r"\\\\|"
        r"."
        r")"
        r")\s*?'",
        re.DOTALL
    )

    char_matches = char_pattern.findall(array_content)

    if char_matches:
        for char_match in char_matches:
            processed_char = process_escape_sequences(char_match, supports_unicode=False)

            if not processed_char:
                print(f"Warning: Failed to process escape sequence: {char_match}")
                continue

            if len(processed_char) != 1:
                print(f"Warning: Processed character should be single byte but got: {processed_char}")

            for char in processed_char:
                char_code = ord(char)
                if char_code < 256:
                    full_bytes.append(char_code)
                else:
                    print(f"Warning: Character code out of byte range: {char_code}")
                    full_bytes.append(char_code & 0xFF)

    if full_bytes:
        return bytes(full_bytes)

    full_string = ""
    string_pattern = re.compile(r'"((?:\\"|[^"])*)"', re.DOTALL)
    for match in string_pattern.finditer(array_content):
        escaped_string = match.group(1)
        full_string += escaped_string

    if full_string:
        processed_string = process_escape_sequences(full_string)
        raw_bytes = processed_string.encode("latin-1")
        return raw_bytes

    print("No valid descriptor data found in C++ code")
    return None

def process_go_escape_sequences(s: str) -> bytes:
    out = bytearray()
    i = 0
    n = len(s)

    while i < n:
        c = s[i]

        # 普通字符，UTF-8 编码
        if c != '\\':
            out.extend(c.encode('utf-8'))
            i += 1
            continue

        # 处理转义
        i += 1
        if i >= n:
            raise ValueError("Incomplete escape sequence")

        esc = s[i]
        i += 1

        if esc == 'a':
            out.append(0x07)
        elif esc == 'b':
            out.append(0x08)
        elif esc == 'f':
            out.append(0x0C)
        elif esc == 'n':
            out.append(0x0A)
        elif esc == 'r':
            out.append(0x0D)
        elif esc == 't':
            out.append(0x09)
        elif esc == 'v':
            out.append(0x0B)
        elif esc == '\\':
            out.append(0x5C)
        elif esc == '"':
            out.append(0x22)
        elif esc == "'":
            out.append(0x27)

        # 八进制 \NNN（最多 3 位）
        elif esc in '01234567':
            digits = esc
            for _ in range(2):
                if i < n and s[i] in '01234567':
                    digits += s[i]
                    i += 1
                else:
                    break
            val = int(digits, 8)
            if val > 255:
                raise ValueError("Octal escape out of range")
            out.append(val)

        # 十六进制 \xNN（单字节）
        elif esc == 'x':
            if i + 1 >= n:
                raise ValueError("Incomplete \\x escape")
            hex_digits = s[i:i+2]
            out.append(int(hex_digits, 16))
            i += 2

        # Unicode \uXXXX
        elif esc == 'u':
            hex_digits = s[i:i+4]
            codepoint = int(hex_digits, 16)
            out.extend(chr(codepoint).encode('utf-8'))
            i += 4

        # Unicode \UNNNNNNNN
        elif esc == 'U':
            hex_digits = s[i:i+8]
            codepoint = int(hex_digits, 16)
            if codepoint > 0x10FFFF:
                raise ValueError("Unicode out of range")
            out.extend(chr(codepoint).encode('utf-8'))
            i += 8

        else:
            raise ValueError(f"Unknown escape sequence: \\{esc}")

    return bytes(out)

def process_escape_sequences(escaped_string, supports_unicode=True):
    if supports_unicode:
        def replace_unicode(match):
            hex_str = match.group(1)
            if len(hex_str) % 2 != 0:
                hex_str = '0' + hex_str

            return bytes.fromhex(hex_str).decode('latin-1')

        escaped_string = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            replace_unicode,
            escaped_string
        )

        escaped_string = re.sub(
            r"\\U([0-9a-fA-F]{8})",
            replace_unicode,
            escaped_string
        )

        if '\\x{' in escaped_string:
            escaped_string = re.sub(
                r"\\x\{([0-9a-fA-F]{2,6})\}",
                replace_unicode,
                escaped_string
            )

    def replace_octal(match):
        octal_str = match.group(1)
        char_code = int(octal_str, 8)
        return chr(char_code) if char_code < 256 else f"\\{octal_str}"

    escaped_string = re.sub(
        r"\\([0-7]{1,3})",
        replace_octal,
        escaped_string
    )

    def replace_hex(match):
        hex_str = match.group(1)
        char_code = int(hex_str, 16)
        return chr(char_code)

    escaped_string = re.sub(
        r"\\x([0-9a-fA-F]{2})",
        replace_hex,
        escaped_string
    )

    simple_escapes = {
        "\\a": "\a",
        "\\b": "\b",
        "\\f": "\f",
        "\\n": "\n",
        "\\r": "\r",
        "\\t": "\t",
        "\\\"": "\"",
        "\\'": "'",
        "\\\\": "\\",
        "\\v": "\v",
        "\\0": "\0",
        '\\$': '$',
        '\\{': '{',
        '\\}': '}',
        "\\e": "\x1b",
        "\\?": "?",
    }

    for esc, replacement in simple_escapes.items():
        escaped_string = escaped_string.replace(esc, replacement)

    return escaped_string

def parse_go_byte_array(byte_array):
    byte_array = byte_array.replace('\n', '')
    byte_array = byte_array.replace(' ', '')
    byte_array = byte_array.strip()

    byte_strs = byte_array.split(',')
    data = bytearray()

    for byte_str in byte_strs:
        byte_str = byte_str.strip()
        if not byte_str:
            continue

        if byte_str.startswith('0x'):
            try:
                hex_str = byte_str[2:]
                if len(hex_str) == 1:
                    hex_str = '0' + hex_str
                data.append(int(hex_str, 16))
            except ValueError:
                print(f"Invalid hex byte: {byte_str}")
                return None
        else:
            try:
                value = int(byte_str)
                if value < 0 or value > 255:
                    print(f"Byte value out of range: {value}")
                    return None
                data.append(value)
            except ValueError:
                print(f"Invalid decimal byte: {byte_str}")
                return None

    return bytes(data)
