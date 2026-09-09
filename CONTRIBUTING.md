# Contributing to LitScan

Thank you for your interest in contributing to LitScan! This document provides guidelines for contributing to the project.

## How to Contribute

### Reporting Issues

- Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) for bugs
- Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md) for new features
- Provide as much detail as possible

### Pull Requests

1. Fork the repository
2. Create a new branch (`git checkout -b feature/your-feature-name`)
3. Make your changes
4. Run tests if applicable
5. Commit your changes (`git commit -m 'Add some feature'`)
6. Push to the branch (`git push origin feature/your-feature-name`)
7. Open a Pull Request

### Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and concise

### Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less

## Development Setup

```bash
# Clone the repository
git clone https://github.com/LPK3215/LitScan.git
cd LitScan

# Install dependencies
pip install -r requirements.txt

# Run the tests (no network requests required)
python test_edge.py
python test_server_edge.py

# Run the development server
python litscan.py --serve
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
