# Sadeh API Documentation

This directory contains the OpenAPI (formerly Swagger) specification for the Sadeh application's REST API.

## API Documentation

The complete API documentation is available in the `openapi.yaml` file in this directory. This is an [OpenAPI 3.0.3](https://spec.openapis.org/oas/v3.0.3) specification that documents all endpoints, request/response formats, and data models for the Sadeh application.

## Viewing the API Documentation

There are several ways to view and interact with this documentation:

### Option 1: GitHub-Compatible Viewers

Several GitHub-compatible OpenAPI viewers are available as browser extensions:
- [Swagger Viewer](https://chrome.google.com/webstore/detail/swagger-viewer/nfmkaonpdmaglhjjlggfhlndofdldfag) for Chrome
- [OpenAPI Viewer](https://github.com/koumoul-dev/openapi-viewer-extension) for Chrome/Firefox

Once installed, you can view the OpenAPI documentation directly in GitHub by clicking on the `openapi.yaml` file.

### Option 2: Use Swagger UI Docker (No Installation Required)

You can quickly view the documentation using Docker:

```bash
docker run -p 8080:8080 -e SWAGGER_JSON=/api/openapi.yaml -v /path/to/sadeh/api:/api swaggerapi/swagger-ui
```

Then open your browser and navigate to: http://localhost:8080

### Option 3: Use the Swagger Editor Online

1. Go to [Swagger Editor](https://editor.swagger.io/)
2. Open the `openapi.yaml` file
3. Copy its contents and paste into the editor

## API Structure

The API is organized into the following sections:

- **Authentication**: User login, logout, account management
- **Conversations**: Chat conversation creation and management
- **AI Models**: Interaction with AI models, model selection
- **Documents**: Document upload and management for context
- **Voice**: Voice recording and synthesis
- **RAG**: Retrieval-Augmented Generation features
- **Admin**: Administrative functions for user/role management

## Making Changes

If you need to update the API documentation, simply edit the `openapi.yaml` file directly. The OpenAPI format is designed to be human-readable while also being machine-parsable.
