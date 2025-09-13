import sys
import argparse
from pathlib import Path
from descriptor_extractor import extract_descriptor_data
from proto_generator import generate_proto_file
from prost_extractor import convert_rust_to_proto
import zig_extractor
import betterproto_extractor
import protobufnet_extractor
import pbn_vb_extractor

def unquote_argument(arg):
    if arg.startswith('"') and arg.endswith('"'):
        return arg[1:-1]
    return arg

def print_usage():
    print("Usage:")
    print("  --input, -i     Input file or directory path.")
    print("  --output, -o    Output directory path.")
    print("  --lang, -l      Source language.")
    print("  --help, -h      Display this help message.")

def process_file(file_path, output_dir, source_language, source_code):
    if source_language == "prost":
        proto_content = convert_rust_to_proto(source_code)
        output_file = output_dir / (file_path.stem + ".proto")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(proto_content)

        print(f"Generated: {output_file}")
    elif source_language == "zig":
        proto_content = zig_extractor.convert_proto(source_code)
        output_file = output_dir / (file_path.stem + ".proto")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(proto_content)

        print(f"Generated: {output_file}")
    elif source_language == "betterproto":
        proto_content = betterproto_extractor.convert_proto(source_code)
        output_file = output_dir / (file_path.stem + ".proto")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(proto_content)

        print(f"Generated: {output_file}")
    elif source_language == "pbn":
        proto_content = protobufnet_extractor.convert_proto(source_code)
        output_file = output_dir / (file_path.stem + ".proto")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(proto_content)

        print(f"Generated: {output_file}")
    elif source_language == "pbnvb":
        proto_content = pbn_vb_extractor.convert_proto(source_code)
        output_file = output_dir / (file_path.stem + ".proto")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(proto_content)

        print(f"Generated: {output_file}")
    else:
        descriptor_data = extract_descriptor_data(source_code, source_language)
        if not descriptor_data:
            if input_path.is_file():
                raise ValueError("DescriptorData not found in source code")
            else:
                print(f"Warning: DescriptorData not found in {file_path}. Skipping.")
                return

        generate_proto_file(descriptor_data, output_dir, source_code, source_language)

if __name__ == "__main__":
    input_path = None
    output_dir = None
    source_language = None

    if input_path is None or output_dir is None or source_language is None:
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
            "-l", "--lang",
            dest="source_language",
            choices=["csharp", "java", "go", "python", "ruby", "php", "cpp", "prost", "zig", "betterproto", "pbn", "pbnvb"],
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

        if args.input_path and args.output_directory and args.source_language:
            input_path = Path(unquote_argument(args.input_path))
            output_dir = Path(unquote_argument(args.output_directory))
            source_language = args.source_language.lower()
    else:
        input_path = Path(input_path)
        output_dir = Path(output_dir)

    if input_path is None or output_dir is None or source_language is None:
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

            process_file(input_path, output_dir, source_language, source_code)

        elif input_path.is_dir():
            if source_language == "csharp" or source_language == "pbn":
                file_pattern = "*.cs"
            elif source_language == "java":
                file_pattern = "*.java"
            elif source_language == "go":
                file_pattern = "*.go"
            elif source_language == "python" or source_language == "betterproto":
                file_pattern = "*.py"
            elif source_language == "ruby":
                file_pattern = "*.rb"
            elif source_language == "php":
                file_pattern = "*.php"
            elif source_language == "cpp":
                file_pattern = "*.cc"
            elif source_language == "prost":
                file_pattern = "*.rs"
            elif source_language == "zig":
                file_pattern = "*.zig"
            elif source_language == "pbnvb":
                file_pattern = "*.vb"
            else:
                raise ValueError(f"Unsupported language: {source_language}")

            source_files = list(input_path.rglob(file_pattern))

            if not source_files:
                print(f"No {file_pattern} files found in {input_path}")
                sys.exit()

            for file_path in source_files:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        source_code = f.read()

                    process_file(file_path, output_dir, source_language, source_code)

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
