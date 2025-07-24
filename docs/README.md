# Sadeh API Documentation with Swagger UI

This directory contains the files needed to display the Sadeh API documentation using Swagger UI through GitHub Pages.

## How to Enable GitHub Pages

To make this interactive Swagger UI documentation available online:

1. Push this branch to GitHub
2. Go to your GitHub repository
3. Navigate to Settings > Pages
4. Under "Source", select the branch containing these docs (e.g., "refactor-db-and-api-docs")
5. Select the "/docs" folder
6. Click Save

After a few minutes, GitHub will provide you with a URL where your documentation is published (typically https://[your-username].github.io/sadeh/).

## How It Works

- `index.html`: Contains the Swagger UI setup that loads and displays the OpenAPI specification
- `openapi.yaml`: The OpenAPI specification defining all API endpoints

## Local Preview

To preview this documentation locally before pushing to GitHub:

```bash
cd /path/to/sadeh/docs
python -m http.server 8000
```

Then open your browser and navigate to: http://localhost:8000
