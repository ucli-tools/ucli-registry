# UCLI Registry

Official registry of UCLI Tools - Professional CLI utilities for developers.

## Overview

This registry catalogs official UCLI Tools that can be installed and managed using the `ucli` tool manager. Tools listed here are discoverable via `ucli list` and can be installed with simple commands:

```bash
ucli build gits mdtexpdf mdaudiobook
```

## Registry Structure

```
ucli-registry/
├── registry/
│   ├── apps.yaml              # Main official tools registry
│   └── community/             # Community-contributed tools
│       └── community.yaml
├── docs/
│   ├── submit-tool.md         # How to submit your tool
│   ├── verification.md        # Verification process
│   └── tool-guidelines.md     # Tool development guidelines
└── README.md                   # This file
```

## Quick Start

### Using Official Tools

```bash
# Install ucli tool manager first
curl -fsSL https://install.ucli.tools | bash

# List all available tools
ucli list

# Install popular tools
ucli build gits mdtexpdf mdaudiobook

# Update all tools
ucli update
```

### Using Community Tools

```bash
# Install from any GitHub repo (use at your own risk)
ucli build username/tool-name
```

## Tool Categories

### Official Tools (ucli-tools)

Maintained by the UCLI Tools team:
- **ucli** - Tool manager and installer
- **gits** - Git workflow automation
- **mdtexpdf** - Markdown to PDF converter
- **mdaudiobook** - Text-to-speech audiobook generator

### Community Tools

Community-contributed tools that have been reviewed and approved:
- Submit a PR to get your tool listed!
- [See submission guidelines →](docs/submit-tool.md)

## Submitting Your Tool

1. **Develop your tool** following our [guidelines](docs/tool-guidelines.md)
2. **Test thoroughly** with `ucli build ./your-tool`
3. **Submit PR** adding your tool to `apps.community` in `registry/apps.yaml`
4. **Automated validation** - GitHub Actions validates your tool
5. **Review process** - Team reviews code, security, documentation
6. **Approved!** - Tool appears in `ucli list`

[Read full submission guide →](docs/submit-tool.md)

## Tool Requirements

All tools must include:

- ✅ `Makefile` - Build instructions with `install` target
- ✅ `README.md` - Clear documentation and usage examples
- ✅ Compatible with `ucli build` workflow
- ✅ No hardcoded secrets or sensitive data
- ✅ Open source license (Apache 2.0 preferred)
- ✅ Cross-platform compatibility (Linux/macOS)

[See detailed guidelines →](docs/tool-guidelines.md)

## Registry Format

```yaml
apps:
  official:
    - name: gits
      repo: github.com/ucli-tools/gits
      description: Git workflow automation supporting Forgejo, Gitea, and GitHub
      pattern: cli
      status: production
      maintainer: ucli-tools
      tags: [git, workflow, automation, forgejo, gitea, github]

  community:
    - name: my-tool
      repo: github.com/username/my-tool
      author: username
      maintainer: username
      submitted_date: 2025-12-22
      status: production
```

## Automated Validation

**GitHub Actions** automatically:
- ✅ Validates YAML syntax
- ✅ Checks schema structure
- ✅ Validates all tool entries
- ✅ Computes statistics dynamically
- ✅ Generates processed registry

## Security

- **Official tools**: Audited and maintained by UCLI Tools team
- **Community tools**: Code reviewed, tested, and security checked
- **External tools**: Use at your own risk - review code first

⚠️ Always review tool code before installing, especially for unverified tools.

## Contributing

We welcome contributions!

- 🐛 [Report issues](https://github.com/ucli-tools/ucli-registry/issues)
- 📝 [Submit tools](docs/submit-tool.md)
- 💬 [Join discussions](https://github.com/orgs/ucli-tools/discussions)

## Support

- **Documentation**: [docs.ucli.tools](https://docs.ucli.tools)
- **Issues**: [GitHub Issues](https://github.com/ucli-tools/ucli-registry/issues)
- **Community**: [Discussions](https://github.com/orgs/ucli-tools/discussions)

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

---

**Version**: 1.0.0
**Last Updated**: 2025-12-22
**Total Tools**: Computed dynamically via CI/CD
**Maintained by**: [UCLI Tools](https://github.com/ucli-tools)
