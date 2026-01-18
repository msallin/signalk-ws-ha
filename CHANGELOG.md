# Changelog

## 1.2.0

### Improvements

- Add possibility to ignore specific event entities from being created.
- Reduce data churn by improving tolerance values and calculations.

### Bugfixes

- Handle case when a access request is denied.

### Miscellaneous

## 1.1.0

### Improvements

- Reduce data churn by improving tolerance values and calculations.
- Refresh doesn't only update entities but also device metadata (server version and user editable values).

### Bug Fixes

- Integration didn't handle certain edge cases after token refresh automatically.
- Already added devices were being displayed under "Discovered" in the UI.

### Miscellaneous

- Push test coverage to 100%.
- Add comments and documentation for clarity throughout the codebase.

## 1.0.0

- Initial public release.
