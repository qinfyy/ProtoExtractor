# JarExtractor

该工具用于从 jar 文件中提取使用 protoc 编译的 Java 类为 protobuf 定义。

## 环境要求
- [JDK17]((https://www.oracle.com/java/technologies/javase/jdk17-archive-downloads.html))

## 用法:
```
.\gradlew.bat jar
cd .\build\libs
java -jar JarProtoExtractor-1.0-SNAPSHOT.jar <args>
```