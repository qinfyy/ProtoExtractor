using System.Collections;
using System.Reflection;
using System.Text;

namespace DotNetProtoExtractor
{
    public class ProtoGenerator
    {
        private Assembly _protobufAssembly = null;
        private Type _originalNameAttributeType = null;
        private Type _iMessageType = null;

        public bool LoadGoogleProtobufAssembly(string protobufDllPath)
        {
            try
            {
                _protobufAssembly = Assembly.LoadFrom(protobufDllPath);
                if (_protobufAssembly == null)
                {
                    Console.WriteLine($"Google.Protobuf.dll assembly not found at: {protobufDllPath}");
                    return false;
                }

                _originalNameAttributeType = _protobufAssembly.GetType("Google.Protobuf.Reflection.OriginalNameAttribute");
                _iMessageType = _protobufAssembly.GetType("Google.Protobuf.IMessage");

                if (_originalNameAttributeType == null || _iMessageType == null)
                {
                    Console.WriteLine("Required types not found in Google.Protobuf.dll assembly.");
                    return false;
                }

                return true;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error loading Google.Protobuf: {ex.Message}");
                return false;
            }
        }

        public void ProcessAssembly(string assemblyPath, string outputPath, string protobufPath)
        {
            if (!LoadGoogleProtobufAssembly(protobufPath))
            {
                Console.WriteLine("Error: Failed to load Google.Protobuf assembly.");
                return;
            }

            var assembly = Assembly.LoadFrom(assemblyPath);
            var sb = new StringBuilder();
            sb.AppendLine("syntax = \"proto3\";\n");

            var messageTypes = GetMessageTypes(assembly);
            var enumTypes = GetOriginalNameEnums(assembly);

            foreach (var enumType in enumTypes)
            {
                sb.AppendLine($"// enum {enumType.FullName}");
                string enumContent = GenerateEnumDefinition(enumType);
                sb.AppendLine(enumContent);
                sb.AppendLine();
            }

            foreach (var messageType in messageTypes)
            {
                sb.AppendLine($"// class {messageType.FullName}");
                string protoContent = GenerateProtoFileString(messageType);
                sb.AppendLine(protoContent);
                sb.AppendLine();
            }

            File.WriteAllText(outputPath, sb.ToString());
        }

        private IEnumerable<Type> GetMessageTypes(Assembly assembly)
        {
            return assembly.GetTypes()
                .Where(t => t.IsClass && t.DeclaringType == null)
                .Where(t => t.GetInterfaces().Any(i => _iMessageType.IsAssignableFrom(i)));
        }

        private IEnumerable<Type> GetOriginalNameEnums(Assembly assembly)
        {
            return assembly.GetTypes()
                .Where(t => t.IsEnum && t.DeclaringType == null)
                .Where(t => t.GetMembers().Any(m =>
                    m.GetCustomAttributes(_originalNameAttributeType, false).Any()));
        }

        public string GenerateProtoFileString(Type protoClass)
        {
            var sb = new StringBuilder();

            var descriptorProperty = protoClass.GetProperty("Descriptor");
            var messageDescriptor = descriptorProperty?.GetValue(null);

            if (messageDescriptor == null)
            {
                return $"// Error: Could not get descriptor for {protoClass.Name}";
            }

            GenerateMessageDefinition(messageDescriptor, protoClass, sb, 0, true);
            return sb.ToString();
        }

        private void GenerateMessageDefinition(
                    object messageDescriptor,
                    Type protoClass,
                    StringBuilder sb,
                    int indentLevel,
                    bool isTopLevel)
        {
            string indent = new string(' ', indentLevel * 4);

            var nameProperty = messageDescriptor.GetType().GetProperty("Name");
            string name = (string)nameProperty.GetValue(messageDescriptor);

            sb.AppendLine($"{indent}message {name} {{");

            var typesType = protoClass.GetNestedTypes(BindingFlags.Public | BindingFlags.NonPublic)
                .FirstOrDefault(t => t.Name == "Types");

            if (typesType != null)
            {
                foreach (var nestedType in typesType.GetNestedTypes(BindingFlags.Public | BindingFlags.NonPublic))
                {
                    if (nestedType.IsEnum)
                    {
                        if (nestedType.GetMembers().Any(m =>
                            m.GetCustomAttributes(_originalNameAttributeType, false).Any()))
                        {
                            sb.AppendLine(GenerateEnumDefinition(nestedType, indentLevel + 1));
                        }
                    }
                }
            }

            var oneofsProperty = messageDescriptor.GetType().GetProperty("Oneofs");
            var oneofsEnumerable = oneofsProperty?.GetValue(messageDescriptor) as IEnumerable;
            if (oneofsEnumerable != null)
            {
                foreach (var oneof in oneofsEnumerable)
                {
                    var oneofNameProperty = oneof.GetType().GetProperty("Name");
                    var oneofName = (string)oneofNameProperty.GetValue(oneof);

                    sb.AppendLine($"{indent}    oneof {oneofName} {{");

                    var oneofFieldsProperty = oneof.GetType().GetProperty("Fields");
                    var oneofFieldsEnumerable = oneofFieldsProperty?.GetValue(oneof) as IEnumerable;
                    if (oneofFieldsEnumerable != null)
                    {
                        foreach (var field in oneofFieldsEnumerable)
                        {
                            sb.AppendLine($"{indent}        {GetFieldTypeString(field)} {GetFieldName(field)} = {GetFieldNumber(field)};");
                        }
                    }

                    sb.AppendLine($"{indent}    }}");
                }
            }

            var fieldsProperty = messageDescriptor.GetType().GetProperty("Fields");
            var fieldCollection = fieldsProperty?.GetValue(messageDescriptor);
            if (fieldCollection != null)
            {
                var inDeclarationOrderMethod = fieldCollection.GetType().GetMethod("InDeclarationOrder");
                IList<object> fieldsList = null;

                if (inDeclarationOrderMethod != null)
                {
                    var fields = inDeclarationOrderMethod.Invoke(fieldCollection, null);
                    if (fields is IEnumerable fieldsEnumerable)
                    {
                        fieldsList = fieldsEnumerable.Cast<object>().ToList();
                    }
                }
                else
                {
                    if (fieldCollection is IEnumerable enumerable)
                    {
                        fieldsList = enumerable.Cast<object>().ToList();
                    }
                }

                if (fieldsList != null)
                {
                    foreach (var field in fieldsList)
                    {
                        var containingOneofProperty = field.GetType().GetProperty("ContainingOneof");
                        var containingOneof = containingOneofProperty?.GetValue(field);
                        if (containingOneof != null) continue;

                        string fieldDefinition = null;
                        var isMapProperty = field.GetType().GetProperty("IsMap");
                        bool isMap = isMapProperty != null && (bool)isMapProperty.GetValue(field);

                        if (isMap)
                        {
                            try
                            {
                                var messageTypeProperty = field.GetType().GetProperty("MessageType");
                                var mapDescriptor = messageTypeProperty?.GetValue(field);

                                if (mapDescriptor != null)
                                {
                                    var mapFieldsProperty = mapDescriptor.GetType().GetProperty("Fields");
                                    var mapFieldCollection = mapFieldsProperty?.GetValue(mapDescriptor);

                                    if (mapFieldCollection != null)
                                    {
                                        var mapInDeclarationOrderMethod = mapFieldCollection.GetType().GetMethod("InDeclarationOrder");
                                        List<object> mapFields = null;

                                        if (mapInDeclarationOrderMethod != null)
                                        {
                                            var mapFieldsResult = mapInDeclarationOrderMethod.Invoke(mapFieldCollection, null);
                                            if (mapFieldsResult is IEnumerable mapFieldsEnumerable)
                                            {
                                                mapFields = mapFieldsEnumerable.Cast<object>().ToList();
                                            }
                                        }
                                        else
                                        {
                                            if (mapFieldCollection is IEnumerable enumerable)
                                            {
                                                mapFields = enumerable.Cast<object>().ToList();
                                            }
                                        }

                                        if (mapFields != null && mapFields.Count >= 2)
                                        {
                                            string keyType = GetFieldTypeString(mapFields[0]);
                                            string valueType = GetFieldTypeString(mapFields[1]);
                                            fieldDefinition = $"map<{keyType}, {valueType}> {GetFieldName(field)} = {GetFieldNumber(field)};";
                                        }
                                        else
                                        {
                                            fieldDefinition = $"// Error: Map fields count {mapFields?.Count} for {GetFieldName(field)}";
                                        }
                                    }
                                    else
                                    {
                                        fieldDefinition = $"// Error: Map fields not found for {GetFieldName(field)}";
                                    }
                                }
                                else
                                {
                                    fieldDefinition = $"// Error: Map descriptor not found for {GetFieldName(field)}";
                                }
                            }
                            catch (Exception ex)
                            {
                                fieldDefinition = $"// Error: Failed to process map field {GetFieldName(field)}: {ex.Message}";
                            }
                        }
                        else
                        {
                            try
                            {
                                var isRepeatedProperty = field.GetType().GetProperty("IsRepeated");
                                bool isRepeated = isRepeatedProperty != null && (bool)isRepeatedProperty.GetValue(field);

                                string typeStr = GetFieldTypeString(field);
                                string repeatedStr = isRepeated ? "repeated " : "";
                                fieldDefinition = $"{repeatedStr}{typeStr} {GetFieldName(field)} = {GetFieldNumber(field)};";
                            }
                            catch (Exception ex)
                            {
                                fieldDefinition = $"// Error: Failed to process field {GetFieldName(field)}: {ex.Message}";
                            }
                        }

                        if (fieldDefinition != null)
                        {
                            sb.AppendLine($"{indent}    {fieldDefinition}");
                        }
                    }
                }
            }

            var nestedTypesProperty = messageDescriptor.GetType().GetProperty("NestedTypes");
            var nestedTypesEnumerable = nestedTypesProperty?.GetValue(messageDescriptor) as IEnumerable;
            var processedNames = new HashSet<string>();

            if (nestedTypesEnumerable != null)
            {
                foreach (var nestedType in nestedTypesEnumerable)
                {
                    var nestedNameProperty = nestedType.GetType().GetProperty("Name");
                    string nestedName = nestedNameProperty != null ? (string)nestedNameProperty.GetValue(nestedType) : null;

                    if (string.IsNullOrEmpty(nestedName) || nestedName.EndsWith("Entry") || processedNames.Contains(nestedName))
                        continue;

                    processedNames.Add(nestedName);
                    sb.AppendLine();

                    var nestedTypeClass = typesType?.GetNestedTypes(BindingFlags.Public | BindingFlags.NonPublic)
                        .FirstOrDefault(t => t.Name == nestedName);

                    if (nestedTypeClass != null)
                    {
                        GenerateMessageDefinition(nestedType, nestedTypeClass, sb, indentLevel + 1, false);
                    }
                }
            }

            sb.Append($"{indent}}}");

            if (!isTopLevel)
                sb.AppendLine();
        }

        private string GenerateEnumDefinition(Type enumType, int indentLevel = 0)
        {
            StringBuilder sb = new StringBuilder();
            string indent = new string(' ', indentLevel * 4);
            sb.AppendLine($"{indent}enum {enumType.Name} {{");

            var names = enumType.GetEnumNames();
            var values = enumType.GetEnumValues().Cast<object>().ToArray();

            for (int i = 0; i < names.Length; i++)
            {
                var memberInfo = enumType.GetMember(names[i])[0];
                var attr = memberInfo.GetCustomAttributes(_originalNameAttributeType, false)
                                     .FirstOrDefault();

                string originalName = names[i];
                if (attr != null)
                {
                    var nameProperty = attr.GetType().GetProperty("Name");
                    originalName = nameProperty != null ? (string)nameProperty.GetValue(attr) : names[i];
                }

                string enumValue = Convert.ToInt32(values[i]).ToString();
                sb.AppendLine($"{indent}    {originalName} = {enumValue};");
            }

            sb.Append($"{indent}}}");
            return sb.ToString();
        }

        private string GetFieldTypeString(object field)
        {
            if (field == null) return "unknown";

            try
            {
                var fieldTypeProperty = field.GetType().GetProperty("FieldType");
                if (fieldTypeProperty == null) return "unknown";

                object fieldTypeValue = fieldTypeProperty.GetValue(field);

                var fieldTypeEnum = _protobufAssembly.GetType("Google.Protobuf.Reflection.FieldType");
                if (fieldTypeEnum == null) return "unknown";

                var enumNames = Enum.GetNames(fieldTypeEnum);
                var enumValues = Enum.GetValues(fieldTypeEnum);

                int index = Array.IndexOf(enumValues.Cast<object>().ToArray(), fieldTypeValue);
                if (index < 0 || index >= enumNames.Length) return "unknown";

                string fieldType = enumNames[index].ToLower();

                switch (fieldType)
                {
                    case "int32": return "int32";
                    case "int64": return "int64";
                    case "uint32": return "uint32";
                    case "uint64": return "uint64";
                    case "sint32": return "sint32";
                    case "sint64": return "sint64";
                    case "fixed32": return "fixed32";
                    case "fixed64": return "fixed64";
                    case "sfixed32": return "sfixed32";
                    case "sfixed64": return "sfixed64";
                    case "float": return "float";
                    case "double": return "double";
                    case "bool": return "bool";
                    case "string": return "string";
                    case "bytes": return "bytes";
                    case "enum":
                        var enumTypeProperty = field.GetType().GetProperty("EnumType");
                        var enumType = enumTypeProperty?.GetValue(field);
                        var enumNameProperty = enumType?.GetType().GetProperty("Name");
                        return enumNameProperty != null ? (string)enumNameProperty.GetValue(enumType) : "unknown_enum";
                    case "message":
                        var messageTypeProperty = field.GetType().GetProperty("MessageType");
                        var messageType = messageTypeProperty?.GetValue(field);
                        var msgNameProperty = messageType?.GetType().GetProperty("Name");
                        return msgNameProperty != null ? (string)msgNameProperty.GetValue(messageType) : "unknown_message";
                    default: return fieldType.ToLower();
                }
            }
            catch
            {
                return "unknown";
            }
        }

        private string GetFieldName(object field)
        {
            if (field == null) return "unknown";

            try
            {
                var nameProperty = field.GetType().GetProperty("Name");
                return nameProperty != null ? (string)nameProperty.GetValue(field) : "unknown";
            }
            catch
            {
                return "unknown";
            }
        }

        private int GetFieldNumber(object field)
        {
            if (field == null) return 0;

            try
            {
                var numberProperty = field.GetType().GetProperty("FieldNumber");
                return numberProperty != null ? (int)numberProperty.GetValue(field) : 0;
            }
            catch
            {
                return 0;
            }
        }
    }
}