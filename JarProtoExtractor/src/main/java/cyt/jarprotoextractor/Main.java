package cyt.jarprotoextractor;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public class Main {
    private static String inputJar = null;
    private static String outputFile = null;
    private static String protobufJarPath = null;

    public static void main(String[] args) {
        if (!parseArguments(args)) {
            printUsage();
            System.exit(1);
        }

        protobufJarPath = protobufJarPath == null ? inputJar : protobufJarPath;

        try {
            URL[] urls = {
                    new URL("jar:file:" + protobufJarPath + "!/"),
                    new URL("jar:file:" + inputJar + "!/")
            };

            try (URLClassLoader commonClassLoader = new URLClassLoader(urls, Main.class.getClassLoader())) {
                preloadProtobufClasses(protobufJarPath, commonClassLoader);
                List<Class<?>> messageClasses = loadClasses(inputJar, commonClassLoader);

                ProtoGenerator protoGenerator = new ProtoGenerator();
                if (!protoGenerator.loadProtobufRuntime(commonClassLoader)) {
                    System.err.println("Failed to load Protobuf runtime from: " + protobufJarPath);
                    System.exit(3);
                }

                String protoContent = protoGenerator.generateProtoContent(messageClasses);
                try (FileOutputStream fos = new FileOutputStream(outputFile)) {
                    fos.write(protoContent.getBytes());
                }
                System.out.println("Generated: " + outputFile);
            }
        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            e.printStackTrace();
            System.exit(2);
        }
    }

    private static void preloadProtobufClasses(String protobufJarPath, URLClassLoader classLoader) throws IOException {
        try (JarFile jarFile = new JarFile(new File(protobufJarPath))) {
            Enumeration<JarEntry> entries = jarFile.entries();

            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                String entryName = entry.getName();

                if (entryName.startsWith("com/google/protobuf/") && entryName.endsWith(".class") && !entryName.endsWith("/")) {
                    String className = entryName.replace('/', '.').substring(0, entryName.length() - 6);

                    try {
                        classLoader.loadClass(className);
                    } catch (ClassNotFoundException e) {
                        System.err.println("ClassNotFoundException: Could not load class: " + className + " Error: " + e.getMessage());
                    }
                }
            }
        }
    }

    private static boolean parseArguments(String[] args) {
        for (int i = 0; i < args.length; i++) {
            String arg = args[i];
            switch (arg) {
                case "-i":
                case "--input":
                    if (i + 1 >= args.length) return false;
                    inputJar = args[++i].replaceAll("^\"|\"$", "");
                    break;
                case "-o":
                case "--output":
                    if (i + 1 >= args.length) return false;
                    outputFile = args[++i].replaceAll("^\"|\"$", "");
                    break;
                case "-p":
                case "--protobuf":
                    if (i + 1 >= args.length) return false;
                    protobufJarPath = args[++i].replaceAll("^\"|\"$", "");
                    break;
                case "-h":
                case "--help":
                    printUsage();
                    System.exit(0);
                    break;
                default:
                    System.err.println("Unknown option: " + arg);
                    return false;
            }
        }
        return inputJar != null && outputFile != null;
    }

    private static void printUsage() {
        System.out.println("Usage:");
        System.out.println("  --input, -i     Specify input JAR file");
        System.out.println("  --output, -o    Specify output proto file");
        System.out.println("  --protobuf, -p  Specify Protobuf runtime JAR file");
        System.out.println("  --help, -h      Show this help message");
    }

    public static List<Class<?>> loadClasses(String jarPath, URLClassLoader classLoader) throws IOException {
        List<Class<?>> matchingClasses = new ArrayList<>();

        try (JarFile jarFile = new JarFile(new File(jarPath))) {
            Enumeration<JarEntry> entries = jarFile.entries();

            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                String entryName = entry.getName();

                if (entryName.endsWith(".class")) {
                    String className = entryName.replace('/', '.').substring(0, entryName.length() - 6);

                    if (className.startsWith("com.google.protobuf")) {
                        continue;
                    }

                    try {
                        Class<?> clazz = classLoader.loadClass(className);

                        if (clazz.getEnclosingClass() != null) {
                            continue;
                        }

                        Field field = clazz.getDeclaredField("descriptor");
                        if (Modifier.isPrivate(field.getModifiers()) &&
                                Modifier.isStatic(field.getModifiers()) &&
                                field.getType().getName().equals("com.google.protobuf.Descriptors$FileDescriptor")) {

                            matchingClasses.add(clazz);
                        }
                    } catch (ClassNotFoundException e) {
                        System.err.println("ClassNotFoundException: Could not load class: " + className + " Error: " + e.getMessage());
                    } catch (NoClassDefFoundError e) {
                        System.err.println("NoClassDefFoundError: Could not load class: " + className + " Error: " + e.getMessage());
                    } catch (NoSuchFieldException | SecurityException ignored) {
                    } catch (Exception ex) {
                        System.err.println("Unexpected error with class: " + className + " Error: " + ex.getMessage());
                    }
                }
            }
        }
        return matchingClasses;
    }
}