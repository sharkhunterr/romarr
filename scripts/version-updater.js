/**
 * standard-version custom updater for `romarr/src/romarr/__init__.py`.
 *
 * Keeps the Python package's ``__version__`` string in lock-step with
 * package.json + pyproject.toml on every release bump.
 */

const versionRegex = /__version__\s*=\s*["']([^"']+)["']/;

module.exports.readVersion = function (contents) {
  const match = contents.match(versionRegex);
  if (match) {
    return match[1];
  }
  throw new Error('Could not find __version__ in __init__.py');
};

module.exports.writeVersion = function (contents, version) {
  return contents.replace(versionRegex, `__version__ = "${version}"`);
};
