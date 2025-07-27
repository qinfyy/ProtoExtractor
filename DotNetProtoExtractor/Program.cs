namespace DotNetProtoExtractor
{
    internal class Program
    {
        public static void Main(string[] args)
        {
            string assemblyPath = null;
            string outputPath = null;
            string mode = null;
            string protobufPath = "./Google.Protobuf.dll";

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--input" || args[i] == "-i")
                {
                    if (i + 1 < args.Length)
                    {
                        assemblyPath = args[i + 1].Trim('"');
                        i++;
                    }
                    else
                    {
                        Console.WriteLine("Error: Missing argument for '--input' or '-i'.");
                        return;
                    }
                }
                else if (args[i] == "--output" || args[i] == "-o")
                {
                    if (i + 1 < args.Length)
                    {
                        outputPath = args[i + 1].Trim('"');
                        i++;
                    }
                    else
                    {
                        Console.WriteLine("Error: Missing argument for '--output' or '-o'.");
                        return;
                    }
                }
                else if (args[i] == "--mode" || args[i] == "-m")
                {
                    if (i + 1 < args.Length)
                    {
                        mode = args[i + 1].ToLower();
                        i++;
                    }
                    else
                    {
                        Console.WriteLine("Error: Missing argument for '--mode' or '-m'.");
                        return;
                    }
                }
                else if (args[i] == "--help" || args[i] == "-h")
                {
                    PrintUsage();
                    return;
                }
                else if (args[i] == "--protobuf" || args[i] == "-p")
                {
                    if (i + 1 < args.Length)
                    {
                        protobufPath = args[i + 1].Trim('"');
                        i++;
                    }
                    else
                    {
                        Console.WriteLine("Error: Missing argument for '--protobuf' or '-p'.");
                        return;
                    }
                }
            }

            if (string.IsNullOrEmpty(assemblyPath) || string.IsNullOrEmpty(outputPath) || string.IsNullOrEmpty(mode))
            {
                Console.WriteLine("Error: Missing '--input' or '--output' or '--mode' arguments.");
                PrintUsage();
                return;
            }

            try
            {
                switch (mode)
                {
                    case "google":
                        var googleGenerator = new ProtoGenerator();
                        googleGenerator.ProcessAssembly(assemblyPath, outputPath, protobufPath);
                        break;

                    case "protobuf-net":
                        var pbnGenerator = new ProtoBufNetGenerator();
                        pbnGenerator.ProcessAssembly(assemblyPath, outputPath);
                        break;

                    default:
                        Console.WriteLine($"Error: Unknown mode '{mode}'. Valid options: 'google' or 'protobuf-net'");
                        return;
                }

                Console.WriteLine($"Generated: {outputPath}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error: {ex}");
                Console.WriteLine(ex.StackTrace);
            }
        }

        private static void PrintUsage()
        {
            Console.WriteLine("Usage:");
            Console.WriteLine("  --input, -i     Input assembly file path.");
            Console.WriteLine("  --output, -o    Output proto file path.");
            Console.WriteLine("  --mode, -m     Analysis mode: 'google' or 'protobuf-net'");
            Console.WriteLine("  --protobuf, -p  Google.Protobuf runtime file path");
            Console.WriteLine("  --help, -h      Display this help message.");
        }
    }
}
