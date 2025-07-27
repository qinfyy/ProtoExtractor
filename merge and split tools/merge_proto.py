import os
import re

def get_proto_files(directory):
    proto_files = []
    for filename in os.listdir(directory):
        if filename.endswith('.proto'):
            proto_files.append(filename)
    return proto_files

def process_proto_file(file_path, remove_comments):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    content = re.sub(r'syntax\s*=\s*"proto3";\s*', '', content)
    content = re.sub(r'option\s+.*?;\s*', '', content, flags=re.DOTALL)
    content = re.sub(r'import\s+"[^"]*";\s*', '', content)
    content = re.sub(r'package\s+[^;]+;\s*', '', content)

    if remove_comments:
        content = re.sub(r'^\s*//.*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'//[^\n]*', '', content)

    return content.strip()

def merge_proto_files(input_dir, output_file):
    remove_comments = True
    new_header = 'syntax = "proto3";\n\noption csharp_namespace = "Proto";'
    files = get_proto_files(input_dir)
    merged_content = []

    merged_content.append(new_header.strip() + '\n')
    
    for file in files:
        file_path = os.path.join(input_dir, file)
        file_content = process_proto_file(file_path, remove_comments)

        merged_content.append(f'// File {file}')
        merged_content.append(file_content)
        merged_content.append('')

    with open(output_file, 'w', encoding='utf-8') as out_file:
        out_file.write('\n'.join(merged_content))
    
    print(f'Merge completed: {output_file}')

if __name__ == '__main__':
    input_dir = './proto_message_files'
    output_file = './merged.proto'

    merge_proto_files(input_dir, output_file)