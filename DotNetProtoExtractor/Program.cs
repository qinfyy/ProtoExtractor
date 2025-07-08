namespace DotNetProtoExtractor
{
    internal class Program
    {
        public static void Main(string[] args)
        {
            string assemblyPath = null;
            string outputPath = null;
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
                else if (args[i] == "--help" || args[i] == "-h")
                {
                    PrintUsage();
                    return;
                }
            }

            if (string.IsNullOrEmpty(assemblyPath) || string.IsNullOrEmpty(outputPath))
            {
                Console.WriteLine("Error: Missing '--input' or '--output' arguments.");
                PrintUsage();
                return;
            }

            try
            {
                var generator = new ProtoGenerator();
                generator.ProcessAssembly(assemblyPath, outputPath, protobufPath);
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
            Console.WriteLine("  --protobuf, -p  Google.Protobuf runtime file path");
            Console.WriteLine("  --help, -h      Display this help message.");
        }
    }
}
