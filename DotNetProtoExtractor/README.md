# DotNetProtoExtractor

该工具用于从 dotnet Assembly 中提取使用 protoc 编译的类为 protobuf 定义。

## 环境要求
- [.NET 9](https://dotnet.microsoft.com/zh-cn/download/dotnet/9.0)

## 用法
```
dotnet build
cd .\bin\Debug\net9.0
.\DotNetProtoExtractor.exe <args>
```