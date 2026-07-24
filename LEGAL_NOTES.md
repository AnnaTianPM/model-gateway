# Legal Notes

## Upstream License

This project is derived from [`zk-2025/model-gateway`](https://github.com/zk-2025/model-gateway),
which is licensed under **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**.

- Upstream commit: `021b259`
- Upstream version: `1.6.0`
- Baseline tag: `baseline-upstream-021b259`

## Attribution

Original author: [zk-2025](https://github.com/zk-2025)
Original project: 无限额度 AI 模型网关 (Unlimited AI API Gateway)

## License Terms

### Permitted (CC BY-NC 4.0)

- **Share** — copy and redistribute the material in any medium or format
- **Adapt** — remix, transform, and build upon the material

### Conditions

- **Attribution** — You must give appropriate credit, provide a link to the license,
  and indicate if changes were made. You may do so in any reasonable manner, but
  not in any way that suggests the licensor endorses you or your use.
- **NonCommercial** — You may not use the material for commercial purposes.

### Not Permitted

- **Commercial use** — without prior authorization from the upstream author
- **Company internal commercial use** — without prior authorization

## Usage Declaration

This derivative project is intended for **personal, non-commercial, home LAN use only**.

If you intend to use this project in a commercial setting or for revenue-generating
purposes, you must:

1. Contact the upstream author (`zk-2025`) to obtain commercial licensing.
2. Alternatively, re-implement the functionality from scratch without referencing
   the upstream codebase.

## Changes from Upstream

This fork makes significant architectural and functional changes:

- Complete modular rewrite (single `app.py` → 15+ modules)
- SQLite database replacing JSON file storage
- Smart routing with static model capability scoring and dynamic health monitoring
- Separated admin/client authentication
- Removed forced language injection
- Removed desktop app mode (pywebview/pystray)
- Added Docker deployment and versioned release workflow
- Added comprehensive test suite

Despite these changes, the core concept and some utility functions derive from the
upstream project. Attribution is retained accordingly.

## Disclaimer

This software is provided "as is" without warranty of any kind. The authors and
contributors are not liable for any damages arising from its use.

## Contact

For commercial licensing inquiries regarding the upstream project, please contact
the original author through their GitHub repository.
