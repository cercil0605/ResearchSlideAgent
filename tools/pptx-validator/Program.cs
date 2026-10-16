using System.Text.Json;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Validation;

if (args.Length == 0)
{
    Console.Error.WriteLine("Usage: dotnet run --project tools/pptx-validator -- file.pptx [...]");
    return 2;
}

var results = new List<object>();
var failed = false;
foreach (var path in args)
{
    using var document = PresentationDocument.Open(path, false);
    var validator = new OpenXmlValidator(FileFormatVersions.Microsoft365) { MaxNumberOfErrors = 0 };
    var errors = validator.Validate(document).Select(error => new
    {
        error.Id,
        Type = error.ErrorType.ToString(),
        error.Description,
        Part = error.Part?.Uri.ToString(),
        Path = error.Path?.XPath,
    }).ToArray();
    failed |= errors.Length > 0;
    results.Add(new { File = path, ErrorCount = errors.Length, Errors = errors });
}

Console.WriteLine(JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true }));
return failed ? 1 : 0;
