# Installation Instructions

## For End Users (Your Coworkers)

### Quick Install from GitHub
```bash
pip install git+https://github.com/yourusername/sandcastle.git
```

Then run from anywhere:
```bash
sandcastle
```

### Manual Install from Source
```bash
git clone https://github.com/yourusername/sandcastle.git
cd sandcastle/Sandcastle
pip install -e .
```

## For Developers

### Development Setup
```bash
git clone https://github.com/yourusername/sandcastle.git
cd sandcastle/Sandcastle
pip install -r requirements.txt
```

Run without installing:
```bash
python -m sandcastle_pkg
```

## Package Structure

```
Sandcastle/
├── pyproject.toml           # Modern Python packaging config
├── requirements.txt         # Dependencies
├── config.json              # User configuration
├── sandcastle_pkg/          # Main package
│   ├── __init__.py
│   ├── __main__.py         # Entry point (sandcastle command)
│   ├── cli/                # Salesforce CLI wrapper
│   ├── utils/              # Utilities (CSV, records, bulk, picklists)
│   ├── phase1/             # Phase 1 creation modules
│   └── phase2/             # Phase 2 update modules
├── fieldData/              # Field metadata CSVs
├── logs/                   # Migration logs
└── migration_data/         # CSV tracking
```

## Updating the Package

After making code changes:
```bash
# If installed with pip install -e .
# Changes are automatically reflected

# If installed normally, reinstall:
pip install --upgrade git+https://github.com/yourusername/sandcastle.git
```
