using System.Text;
using Mono.Cecil;
using Mono.Cecil.Cil;
using ProtoBuf;

namespace DotNetProtoExtractor
{
    public class ProtoBufNetGenerator
    {
        public void ProcessAssembly(string assemblyPath, string outputPath)
        {
            try
            {
                var assembly = AssemblyDefinition.ReadAssembly(assemblyPath);

                var sb = new StringBuilder();
                sb.AppendLine("syntax = \"proto3\";\n");
                sb.AppendLine("package ProtoBufNet;\n");

                foreach (var type in assembly.MainModule.Types)
                {
                    if (type.IsEnum && type.CustomAttributes.Any(a =>
                        a.AttributeType.FullName == typeof(ProtoContractAttribute).FullName))
                    {
                        sb.AppendLine("// enum " + type.FullName);
                        sb.AppendLine(GenerateEnumDefinition(type, 0));
                        sb.AppendLine();
                    }
                }

                foreach (var type in assembly.MainModule.Types)
                {
                    if (type.IsClass && !type.IsNested &&
                        type.CustomAttributes.Any(a =>
                            a.AttributeType.FullName == typeof(ProtoContractAttribute).FullName) &&
                        type.Interfaces.Any(i =>
                            i.InterfaceType.FullName == typeof(IExtensible).FullName))
                    {
                        sb.AppendLine("// class " + type.FullName);
                        sb.AppendLine(GenerateMessageDefinition(type));
                        sb.AppendLine();
                    }
                }

                string messageText = sb.ToString();
                File.WriteAllText(outputPath, messageText);
            }
            catch (Exception ex)
            {
                throw new Exception($"Error processing assembly with protobuf-net: {ex.Message}", ex);
            }
        }

        private string GenerateMessageDefinition(TypeDefinition type)
        {
            var sb = new StringBuilder();
            GenerateMessageContent(type, sb, 0, true);
            return sb.ToString();
        }

        private void GenerateMessageContent(TypeDefinition type, StringBuilder sb, int indentLevel, bool isTopLevel)
        {
            string indent = new string(' ', indentLevel * 4);
            sb.AppendLine($"{indent}message {type.Name} {{");

            var enumNames = new HashSet<string>();

            foreach (var nested in type.NestedTypes)
            {
                if (nested.IsEnum && nested.CustomAttributes
                    .Any(a => a.AttributeType.FullName == typeof(ProtoBuf.ProtoContractAttribute).FullName))
                {
                    enumNames.Add(nested.Name);

                    sb.AppendLine(GenerateEnumDefinition(nested, indentLevel + 1));
                    sb.AppendLine();
                }
            }

            var properties = type.Properties
                .Where(p => p.CustomAttributes
                    .Any(a => a.AttributeType.FullName == typeof(ProtoMemberAttribute).FullName))
                .ToList();

            var oneofGroups = new Dictionary<string, List<PropertyDefinition>>();
            var processedProperties = new List<PropertyDefinition>();

            foreach (var property in properties)
            {
                var resetMethod = type.Methods.FirstOrDefault(m =>
                    m.Name == $"Reset{property.Name}" &&
                    m.Parameters.Count == 0);

                if (resetMethod == null) continue;

                var unionField = FindDiscriminatedUnionField(resetMethod);
                if (unionField == null) continue;

                string groupName = unionField.Name.StartsWith("__pbn__")
                    ? unionField.Name.Substring("__pbn__".Length)
                    : unionField.Name;

                if (!oneofGroups.ContainsKey(groupName))
                    oneofGroups[groupName] = new List<PropertyDefinition>();

                oneofGroups[groupName].Add(property);
                processedProperties.Add(property);
            }

            foreach (var group in oneofGroups)
            {
                sb.AppendLine($"{indent}    oneof {group.Key} {{");

                foreach (var property in group.Value)
                {
                    var protoAttr = property.CustomAttributes
                        .First(a => a.AttributeType.FullName == typeof(ProtoMemberAttribute).FullName);

                    int tag = (int)protoAttr.ConstructorArguments[0].Value;
                    string name = GetProtoMemberName(protoAttr) ?? property.Name;

                    string fieldType = GetProtoTypeString(property.PropertyType,
                        GetDataFormat(protoAttr));

                    sb.AppendLine($"{indent}        {fieldType} {name} = {tag};");
                }

                sb.AppendLine($"{indent}    }}");
                sb.AppendLine();
            }

            foreach (var property in properties)
            {
                if (processedProperties.Contains(property)) continue;

                var protoAttr = property.CustomAttributes
                    .First(a => a.AttributeType.FullName == typeof(ProtoMemberAttribute).FullName);

                int tag = (int)protoAttr.ConstructorArguments[0].Value;
                string fieldType = GetFieldTypeString(property, protoAttr);
                string name = GetProtoMemberName(protoAttr) ?? property.Name;

                sb.AppendLine($"{indent}    {fieldType} {name} = {tag};");
            }

            foreach (var nested in type.NestedTypes)
            {
                if (nested.IsClass &&
                    !enumNames.Contains(nested.Name) &&
                    nested.CustomAttributes
                    .Any(a => a.AttributeType.FullName == typeof(ProtoContractAttribute).FullName) &&
                    nested.Interfaces.Any(i =>
                        i.InterfaceType.FullName == typeof(IExtensible).FullName))
                {
                    sb.AppendLine();
                    GenerateMessageContent(nested, sb, indentLevel + 1, false);
                }
            }

            sb.Append($"{indent}}}");
            if (!isTopLevel) sb.AppendLine();
        }

        private FieldDefinition FindDiscriminatedUnionField(MethodDefinition resetMethod)
        {
            if (resetMethod?.Body == null) return null;

            foreach (var instruction in resetMethod.Body.Instructions)
            {
                if (instruction.OpCode.Code != Code.Ldflda) continue;

                var fieldRef = instruction.Operand as FieldReference;
                if (fieldRef == null) continue;

                var fieldDef = fieldRef.Resolve();
                if (fieldDef == null) continue;

                if (fieldDef.FieldType.Namespace == "ProtoBuf" &&
                    fieldDef.FieldType.Name.StartsWith("DiscriminatedUnion"))
                {
                    return fieldDef;
                }
            }
            return null;
        }

        private string GetFieldTypeString(PropertyDefinition property, CustomAttribute protoAttr)
        {
            var typeRef = property.PropertyType;

            if (typeRef.IsGenericInstance &&
                typeRef.GetElementType().FullName == "System.Collections.Generic.Dictionary`2")
            {
                var genericType = (GenericInstanceType)typeRef;

                var protoMapAttr = property.CustomAttributes
                    .FirstOrDefault(a => a.AttributeType.FullName == typeof(ProtoMapAttribute).FullName);

                DataFormat keyFormat = GetMapKeyFormat(protoMapAttr);
                DataFormat valueFormat = GetMapValueFormat(protoMapAttr);

                var keyType = GetProtoTypeString(genericType.GenericArguments[0], keyFormat);
                var valueType = GetProtoTypeString(genericType.GenericArguments[1], valueFormat);

                return $"map<{keyType}, {valueType}>";
            }

            if (typeRef.IsArray || (typeRef.IsGenericInstance &&
                typeRef.GetElementType().FullName == "System.Collections.Generic.List`1"))
            {
                TypeReference elementType = typeRef.IsArray
                    ? ((ArrayType)typeRef).ElementType
                    : ((GenericInstanceType)typeRef).GenericArguments[0];

                string protoType = GetProtoTypeString(elementType,
                    GetDataFormat(protoAttr));

                return elementType.FullName == "System.Byte" && typeRef.IsArray
                    ? "bytes"
                    : $"repeated {protoType}";
            }

            return GetProtoTypeString(typeRef, GetDataFormat(protoAttr));
        }

        private DataFormat GetDataFormat(CustomAttribute protoAttr)
        {
            var formatArg = protoAttr.Properties
                .FirstOrDefault(p => p.Name == "DataFormat");
            return formatArg.Argument.Value != null
                ? (DataFormat)formatArg.Argument.Value
                : DataFormat.Default;
        }

        private DataFormat GetMapKeyFormat(CustomAttribute protoMapAttr)
        {
            if (protoMapAttr == null) return DataFormat.Default;

            var formatArg = protoMapAttr.Properties
                .FirstOrDefault(p => p.Name == "KeyFormat");
            return formatArg.Argument.Value != null
                ? (DataFormat)formatArg.Argument.Value
                : DataFormat.Default;
        }

        private DataFormat GetMapValueFormat(CustomAttribute protoMapAttr)
        {
            if (protoMapAttr == null) return DataFormat.Default;

            var formatArg = protoMapAttr.Properties
                .FirstOrDefault(p => p.Name == "ValueFormat");
            return formatArg.Argument.Value != null
                ? (DataFormat)formatArg.Argument.Value
                : DataFormat.Default;
        }

        private string GenerateEnumDefinition(TypeDefinition enumType, int indentLevel)
        {
            StringBuilder sb = new StringBuilder();
            string indent = new string(' ', indentLevel * 4);
            sb.AppendLine($"{indent}enum {enumType.Name} {{");

            foreach (var field in enumType.Fields.Where(f => f.IsStatic))
            {
                var protoAttr = field.CustomAttributes
                    .FirstOrDefault(a => a.AttributeType.FullName == typeof(ProtoEnumAttribute).FullName);

                string name = protoAttr?.Properties
                    .FirstOrDefault(p => p.Name == "Name").Argument.Value as string ?? field.Name;

                int value = (int)field.Constant;
                sb.AppendLine($"{indent}    {name} = {value};");
            }

            sb.Append($"{indent}}}");
            return sb.ToString();
        }

        private string GetProtoTypeString(TypeReference typeRef, DataFormat dataFormat)
        {
            string fullName = typeRef.FullName;

            switch (fullName)
            {
                case "System.Int32" when dataFormat == DataFormat.FixedSize:
                    return "sfixed32";
                case "System.Int64" when dataFormat == DataFormat.FixedSize:
                    return "sfixed64";
                case "System.UInt32" when dataFormat == DataFormat.FixedSize:
                    return "fixed32";
                case "System.UInt64" when dataFormat == DataFormat.FixedSize:
                    return "fixed64";
                case "System.Int32" when dataFormat == DataFormat.ZigZag:
                    return "sint32";
                case "System.Int64" when dataFormat == DataFormat.ZigZag:
                    return "sint64";
            }

            switch (fullName)
            {
                case "System.Int32":
                    return "int32";
                case "System.Int64":
                    return "int64";
                case "System.UInt32":
                    return "uint32";
                case "System.UInt64":
                    return "uint64";
                case "System.Single":
                    return "float";
                case "System.Double":
                    return "double";
                case "System.Boolean":
                    return "bool";
                case "System.String":
                    return "string";
                case "System.Byte[]":
                    return "bytes";

                default:
                    return fullName.Split('.', '/', '+').Last();
            }
        }

        private string GetProtoMemberName(CustomAttribute protoAttr)
        {
            var nameProperty = protoAttr.Properties.FirstOrDefault(p => p.Name == "Name");
            if (nameProperty.Argument.Value != null)
            {
                return nameProperty.Argument.Value.ToString();
            }
            return null;
        }
    }
}
