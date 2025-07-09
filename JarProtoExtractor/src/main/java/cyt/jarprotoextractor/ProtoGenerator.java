package cyt.jarprotoextractor;

import java.lang.reflect.Method;
import java.util.List;
import java.util.Set;
import java.util.HashSet;

public class ProtoGenerator {
    private static final String MAP_ENTRY_SUFFIX = "Entry";

    private Class<?> fileDescriptorClass;
    private Class<?> descriptorClass;
    private Class<?> fieldDescriptorClass;
    private Class<?> enumDescriptorClass;
    private Class<?> enumValueDescriptorClass;
    private Class<?> oneofDescriptorClass;
    private Class<?> javaTypeClass;

    public boolean loadProtobufRuntime(ClassLoader commonClassLoader) {
        try {
            fileDescriptorClass = commonClassLoader.loadClass("com.google.protobuf.Descriptors$FileDescriptor");
            descriptorClass = commonClassLoader.loadClass("com.google.protobuf.Descriptors$Descriptor");
            fieldDescriptorClass = commonClassLoader.loadClass("com.google.protobuf.Descriptors$FieldDescriptor");
            enumDescriptorClass = commonClassLoader.loadClass("com.google.protobuf.Descriptors$EnumDescriptor");
            enumValueDescriptorClass = commonClassLoader.loadClass("com.google.protobuf.Descriptors$EnumValueDescriptor");
            oneofDescriptorClass = commonClassLoader.loadClass("com.google.protobuf.Descriptors$OneofDescriptor");
            javaTypeClass = commonClassLoader.loadClass("com.google.protobuf.Descriptors$FieldDescriptor$JavaType");

            return true;
        } catch (Exception e) {
            System.err.println("Failed to load Protobuf runtime: " + e.getMessage());
            e.printStackTrace();
            return false;
        }
    }

    public String generateProtoContent(List<Class<?>> messageClasses) throws Exception {
        StringBuilder protoContent = new StringBuilder("syntax = \"proto3\";\n\n");
        Set<Object> processedEnums = new HashSet<>();
        Set<Object> processedMessages = new HashSet<>();

        for (Class<?> clazz : messageClasses) {
            Object fileDescriptor = getDescriptor(clazz);
            if (fileDescriptor != null) {
                protoContent.append("// ").append(clazz).append("\n");
                processFileDescriptorEnums(fileDescriptor, protoContent, processedEnums);

                Method getMessageTypes = fileDescriptorClass.getMethod("getMessageTypes");
                @SuppressWarnings("unchecked")
                List<Object> messageDescriptors = (List<Object>) getMessageTypes.invoke(fileDescriptor);

                for (Object messageDescriptor : messageDescriptors) {
                    if (processedMessages.add(messageDescriptor)) {
                        generateMessage(messageDescriptor, protoContent, 0, true, processedEnums);
                        protoContent.append("\n");
                    }
                }
            }
        }
        return protoContent.toString();
    }

    private void processFileDescriptorEnums(Object descriptor,
                                            StringBuilder sb,
                                            Set<Object> processed) throws Exception {
        Method getEnumTypes = fileDescriptorClass.getMethod("getEnumTypes");
        @SuppressWarnings("unchecked")
        List<Object> enumDescs = (List<Object>) getEnumTypes.invoke(descriptor);

        for (Object enumDesc : enumDescs) {
            if (processed.add(enumDesc)) {
                generateEnum(enumDesc, sb, 0);
            }
        }
    }

    private void generateEnum(Object enumDesc,
                              StringBuilder sb,
                              int indentLevel) throws Exception {
        Method getName = enumDescriptorClass.getMethod("getName");
        String name = (String) getName.invoke(enumDesc);

        String indent = "    ".repeat(indentLevel);
        sb.append(indent).append("enum ").append(name).append(" {\n");

        Method getValues = enumDescriptorClass.getMethod("getValues");
        @SuppressWarnings("unchecked")
        List<Object> values = (List<Object>) getValues.invoke(enumDesc);

        for (Object value : values) {
            Method getValueName = enumValueDescriptorClass.getMethod("getName");
            String valueName = (String) getValueName.invoke(value);

            Method getValueNumber = enumValueDescriptorClass.getMethod("getNumber");
            int valueNumber = (int) getValueNumber.invoke(value);

            sb.append(indent).append("    ")
                    .append(valueName)
                    .append(" = ")
                    .append(valueNumber)
                    .append(";\n");
        }
        sb.append(indent).append("}\n\n");
    }

    private Object getDescriptor(Class<?> messageClass) throws Exception {
        try {
            Method getDescriptor = messageClass.getMethod("getDescriptor");
            return getDescriptor.invoke(null);
        } catch (NoSuchMethodException e) {
            return null;
        }
    }

    private void generateMessage(Object messageDescriptor,
                                 StringBuilder sb,
                                 int indentLevel,
                                 boolean isTopLevel,
                                 Set<Object> processedEnums) throws Exception {
        Method getName = descriptorClass.getMethod("getName");
        String name = (String) getName.invoke(messageDescriptor);

        String indent = "    ".repeat(indentLevel);
        sb.append(indent).append("message ").append(name).append(" {\n");

        Method getEnumTypes = descriptorClass.getMethod("getEnumTypes");
        @SuppressWarnings("unchecked")
        List<Object> enumDescs = (List<Object>) getEnumTypes.invoke(messageDescriptor);

        for (Object enumDesc : enumDescs) {
            if (processedEnums.add(enumDesc)) {
                generateEnum(enumDesc, sb, indentLevel + 1);
            }
        }

        Method getOneofs = descriptorClass.getMethod("getOneofs");
        @SuppressWarnings("unchecked")
        List<Object> oneofs = (List<Object>) getOneofs.invoke(messageDescriptor);

        for (Object oneof : oneofs) {
            Method getOneofName = oneofDescriptorClass.getMethod("getName");
            String oneofName = (String) getOneofName.invoke(oneof);

            sb.append(indent).append("    oneof ").append(oneofName).append(" {\n");

            Method getFields = oneofDescriptorClass.getMethod("getFields");
            @SuppressWarnings("unchecked")
            List<Object> fields = (List<Object>) getFields.invoke(oneof);

            for (Object field : fields) {
                appendField(field, sb, indentLevel + 2);
            }
            sb.append(indent).append("    }\n");
        }

        Method getFields = descriptorClass.getMethod("getFields");
        @SuppressWarnings("unchecked")
        List<Object> fields = (List<Object>) getFields.invoke(messageDescriptor);

        for (Object field : fields) {
            Method getContainingOneof = fieldDescriptorClass.getMethod("getContainingOneof");
            Object containingOneof = getContainingOneof.invoke(field);
            if (containingOneof != null) continue;

            appendField(field, sb, indentLevel + 1);
        }

        Method getNestedTypes = descriptorClass.getMethod("getNestedTypes");
        @SuppressWarnings("unchecked")
        List<Object> nestedTypes = (List<Object>) getNestedTypes.invoke(messageDescriptor);

        for (Object nested : nestedTypes) {
            String nestedName = (String) getName.invoke(nested);
            if (!nestedName.endsWith(MAP_ENTRY_SUFFIX)) {
                generateMessage(nested, sb, indentLevel + 1, false, processedEnums);
                sb.append("\n");
            }
        }

        sb.append(indent).append("}");
        if (isTopLevel) sb.append("\n");
    }

    private void appendField(Object field,
                             StringBuilder sb,
                             int indentLevel) throws Exception {
        String indent = "    ".repeat(indentLevel);

        Method isRepeated = fieldDescriptorClass.getMethod("isRepeated");
        boolean repeated = (boolean) isRepeated.invoke(field);

        Method isMapField = fieldDescriptorClass.getMethod("isMapField");
        boolean mapField = (boolean) isMapField.invoke(field);

        String modifier = "";
        if (!mapField && repeated) {
            modifier = "repeated ";
        }

        Method getName = fieldDescriptorClass.getMethod("getName");
        String name = (String) getName.invoke(field);

        Method getNumber = fieldDescriptorClass.getMethod("getNumber");
        int number = (int) getNumber.invoke(field);

        String typeName = getTypeName(field);

        if (mapField) {
            Method getMessageType = fieldDescriptorClass.getMethod("getMessageType");
            Object entryDesc = getMessageType.invoke(field);

            Method getFieldsMethod = descriptorClass.getMethod("getFields");
            @SuppressWarnings("unchecked")
            List<Object> entryFields = (List<Object>) getFieldsMethod.invoke(entryDesc);

            Object keyField = null;
            Object valueField = null;
            for (Object entryField : entryFields) {
                String fieldName = (String) getName.invoke(entryField);
                if ("key".equals(fieldName)) {
                    keyField = entryField;
                } else if ("value".equals(fieldName)) {
                    valueField = entryField;
                }
            }

            if (keyField != null && valueField != null) {
                String keyType = getTypeName(keyField);
                String valueType = getTypeName(valueField);
                typeName = String.format("map<%s, %s>", keyType, valueType);
            } else {
                typeName = "map<unknown, unknown>";
            }
        }

        String line = String.format("%s%s%s %s = %d;",
                indent,
                modifier,
                typeName,
                name,
                number);
        sb.append(line).append("\n");
    }

    private String getTypeName(Object field) throws Exception {
        Method getType = fieldDescriptorClass.getMethod("getType");
        Object fieldType = getType.invoke(field);

        Method nameMethod = fieldType.getClass().getMethod("name");
        String typeName = ((String) nameMethod.invoke(fieldType)).toUpperCase();

        Method getJavaType = fieldDescriptorClass.getMethod("getJavaType");
        Object javaType = getJavaType.invoke(field);

        Method javaTypeName = javaTypeClass.getMethod("name");
        String javaTypeStr = (String) javaTypeName.invoke(javaType);

        switch (javaTypeStr) {
            case "ENUM":
                Method getEnumType = fieldDescriptorClass.getMethod("getEnumType");
                Object enumType = getEnumType.invoke(field);
                Method getEnumTypeName = enumDescriptorClass.getMethod("getName");
                return (String) getEnumTypeName.invoke(enumType);
            case "MESSAGE":
                Method getMessageType = fieldDescriptorClass.getMethod("getMessageType");
                Object messageType = getMessageType.invoke(field);
                Method getMessageTypeName = descriptorClass.getMethod("getName");
                return (String) getMessageTypeName.invoke(messageType);
        }

        switch (typeName) {
            case "DOUBLE": return "double";
            case "FLOAT": return "float";
            case "INT64": return "int64";
            case "UINT64": return "uint64";
            case "INT32": return "int32";
            case "FIXED64": return "fixed64";
            case "FIXED32": return "fixed32";
            case "STRING": return "string";
            case "BYTES": return "bytes";
            case "UINT32": return "uint32";
            case "SFIXED32": return "sfixed32";
            case "SFIXED64": return "sfixed64";
            case "SINT32": return "sint32";
            case "SINT64": return "sint64";
            case "BOOL": return "bool";
            default: return typeName.toLowerCase();
        }
    }
}