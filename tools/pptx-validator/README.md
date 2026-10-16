# PowerPoint package validation

Microsoft's `DocumentFormat.OpenXml` 3.5.1 validates PresentationML, DrawingML,
relationships and semantic constraints. This is a development/CI tool; .NET is
not installed in the application image.

With .NET SDK 8:

```bash
dotnet run --project tools/pptx-validator -- templates/lab-template.pptx artifacts/eggs/presentation.pptx
```

The command opens inputs read-only, writes a JSON report, and returns nonzero
when validation finds any error. CI checks the bundled template and both demos.
SDK validation does not render slides and cannot prove visual equivalence or
that every PowerPoint version opens the package without repair. Confirm those
separately in PowerPoint on Mac/Windows.

References: [Microsoft validator API](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.validation.openxmlvalidator),
[Microsoft SDK source](https://github.com/dotnet/Open-XML-SDK).
