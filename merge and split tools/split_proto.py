import os
import re

system_names = [
    'uint32', 'uint64', 'int32', 'int64', 'sint32', 'sint64',
    'fixed32', 'fixed64', 'sfixed32', 'sfixed64', 'float', 'double',
    'bool', 'string', 'bytes', 'optional', 'oneof', 'map', 'repeated'
]

def remove_comments(line, state):
    result = []
    i = 0
    n = len(line)
    
    while i < n:
        if state['in_block_comment']:
            if i + 1 < n and line[i] == '*' and line[i+1] == '/':
                state['in_block_comment'] = False
                i += 2
            else:
                i += 1
            continue

        if state['in_string']:
            if line[i] == '"':
                state['in_string'] = False
            elif line[i] == '\\' and i + 1 < n:
                result.append(line[i])
                i += 1
                result.append(line[i])
                i += 1
                continue
            result.append(line[i])
            i += 1
            continue

        if i + 1 < n and line[i] == '/' and line[i+1] == '/':
            break
        elif i + 1 < n and line[i] == '/' and line[i+1] == '*':
            state['in_block_comment'] = True
            i += 2
        elif line[i] == '"':
            state['in_string'] = True
            result.append(line[i])
            i += 1
        else:
            result.append(line[i])
            i += 1
    
    return ''.join(result)

def strip_trailing_comment(line):
    state = {
        'in_block_comment': False,
        'in_string': False
    }
    return remove_comments(line, state)

def extract_top_level_entities(content):
    entities = []
    current = []
    brace_count = 0
    lines = content.splitlines()
    in_entity = False
    entity_type = None
    state = {
        'in_block_comment': False,
        'in_string': False
    }
    
    for original_line in lines:
        clean_line = remove_comments(original_line, state)
        stripped = clean_line.strip()

        if not in_entity and not state['in_block_comment'] and \
           (stripped.startswith("message") or stripped.startswith("enum")):
            if brace_count > 0:
                continue
                
            in_entity = True
            entity_type = "message" if stripped.startswith("message") else "enum"
            current = [original_line]
            brace_count = 1
            continue
        
        if in_entity:
            current.append(original_line)
            
            for char in clean_line:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
            
            if brace_count <= 0:
                entities.append(("\n".join(current), entity_type))
                current = []
                in_entity = False
                brace_count = 0
                entity_type = None
    
    return entities

def format_proto_content(content_str):
    lines = content_str.splitlines()
    result = []
    indent = 0
    state = {
        'in_block_comment': False,
        'in_string': False
    }
    
    for line in lines:
        trimmed_left = line.lstrip()
        
        clean_line = remove_comments(line, state)
        stripped_clean = clean_line.strip()

        if stripped_clean.startswith('}'):
            indent = max(0, indent - 1)

        new_line = ' ' * (indent * 4) + trimmed_left
        result.append(new_line)

        if not stripped_clean.startswith('//') and not state['in_block_comment']:
            count = 0
            temp_state = {
                'in_block_comment': state['in_block_comment'],
                'in_string': state['in_string']
            }
            
            for char in clean_line:
                if temp_state['in_block_comment']:
                    if char == '*' and char == '/':
                        temp_state['in_block_comment'] = False
                    continue
                
                if temp_state['in_string']:
                    if char == '"':
                        temp_state['in_string'] = False
                    elif char == '\\':
                        continue
                    continue
                
                if char == '/':
                    continue
                if char == '{':
                    count += 1
                elif char == '}':
                    count -= 1
            
            indent += max(0, count)
    
    return '\n'.join(result)

def find_locally_defined_types(content):
    locally_defined_types = set()
    lines = content.splitlines()
    brace_level = 0
    state = {
        'in_block_comment': False,
        'in_string': False
    }
    
    for line in lines:
        clean_line = remove_comments(line, state)
        stripped = clean_line.strip()
        if not stripped:
            continue
            
        brace_level += clean_line.count('{')
        brace_level -= clean_line.count('}')

        if brace_level >= 2:
            if stripped.startswith("message") or stripped.startswith("enum"):
                parts = stripped.split()
                if len(parts) > 1:
                    locally_defined_types.add(parts[1])
    
    return locally_defined_types

def extract_field_dependencies(line, top_level_names):
    dependencies = set()

    if not line or line in ['{', '}', ';']:
        return dependencies

    if line.startswith('oneof'):
        return dependencies

    if 'map<' in line or 'MAP<' in line:
        map_types = re.findall(r'[a-zA-Z][a-zA-Z0-9_]*', line)
        for type_name in map_types:
            if type_name in top_level_names and type_name not in system_names:
                dependencies.add(type_name)
        return dependencies

    parts = re.split(r'\s+', line)
    modifiers = {'optional', 'repeated'}
    
    for part in parts:
        if part not in modifiers and part not in system_names and part in top_level_names:
            dependencies.add(part)
        
    return dependencies

def find_dependencies(content, top_level_names):
    dependencies = set()
    lines = content.splitlines()
    brace_count = 0
    state = {
        'in_block_comment': False,
        'in_string': False
    }
    
    for line in lines:
        clean_line = remove_comments(line, state)
        stripped = clean_line.strip()
        if not stripped or stripped.startswith('//'):
            continue
            
        brace_count += clean_line.count('{')
        brace_count -= clean_line.count('}')

        if stripped.startswith('message') or stripped.startswith('enum'):
            continue

        if brace_count >= 1:
            field_deps = extract_field_dependencies(stripped, top_level_names)
            dependencies.update(field_deps)
            
    return dependencies

def save_entity(entity_content, entity_type, top_level_names, output_path):
    entity_name = None
    if entity_type in ["message", "enum"]:
        state = {
            'in_block_comment': False,
            'in_string': False
        }
        
        for line in entity_content.split('\n'):
            clean_line = remove_comments(line, state)
            stripped = clean_line.strip()
            if stripped.startswith("message") or stripped.startswith("enum"):
                parts = stripped.split()
                if len(parts) > 1:
                    entity_name = parts[1]
                    break
                    
        if not entity_name:
            return
            
        filename = f"{entity_name}.proto"
        with open(os.path.join(output_path, filename), 'w') as f:
            f.write("syntax = \"proto3\";\n\n")
            f.write("option java_package = \"emu.lunarcore.proto\";\n\n")

            if entity_type == "message":
                locally_defined_types = find_locally_defined_types(entity_content)
                dependencies = find_dependencies(entity_content, top_level_names)
                
                dependencies = [dep for dep in dependencies if dep not in locally_defined_types]
                
                if dependencies:
                    for dep in sorted(dependencies):
                        f.write(f"import \"{dep}.proto\";\n")
                    f.write("\n")
                    
            formatted_content = format_proto_content(entity_content)
            f.write(formatted_content)
            
            if not formatted_content.endswith('\n'):
                f.write('\n')

def split_proto_file(proto_file_path, output_path):
    os.makedirs(output_path, exist_ok=True)
    with open(proto_file_path, 'r') as f:
        content = f.read()

    entities = extract_top_level_entities(content)

    top_level_names = set()
    state = {
        'in_block_comment': False,
        'in_string': False
    }
    
    for entity_content, entity_type in entities:
        if entity_type in ["message", "enum"]:
            for line in entity_content.split('\n'):
                clean_line = remove_comments(line, state)
                stripped = clean_line.strip()
                if stripped.startswith("message") or stripped.startswith("enum"):
                    parts = stripped.split()
                    if len(parts) > 1:
                        top_level_names.add(parts[1])
    
    for entity_content, entity_type in entities:
        save_entity(entity_content, entity_type, top_level_names, output_path)

if __name__ == "__main__":
    proto_file_path = "InputTest.proto" 
    output_path = "proto_message_files"
    split_proto_file(proto_file_path, output_path)
    print("Proto file split successfully!")
