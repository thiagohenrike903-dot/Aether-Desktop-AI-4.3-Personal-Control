// Enable Windows Developer Mode (allows symlink creation for non-admin users).
// Required for electron-builder on Windows because it needs to extract
// winCodeSign which contains macOS dylib symlinks. Without this, the build
// fails with "Cannot create symbolic link" errors.
//
// Usage:  node build/enable-dev-mode.cjs
// Effect: sets HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock
//         to "AllowDevelopmentWithoutDevLicense" = 1
//         (This still requires admin — see alternatives below.)

const { execSync } = require('child_process');

try {
  execSync(
    'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\AppModelUnlock" ' +
    '/t REG_DWORD /f /v "AllowDevelopmentWithoutDevLicense" /d "1"',
    { stdio: 'inherit' }
  );
  console.log('✓ Developer Mode enabled. Re-run your build.');
} catch (e) {
  console.error('✗ This script needs admin privileges. Two alternatives:');
  console.error('  1. Open PowerShell as Administrator and run:');
  console.error('     reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\AppModelUnlock" /t REG_DWORD /f /v "AllowDevelopmentWithoutDevLicense" /d "1"');
  console.error('  2. Or: Settings → Privacy & security → For developers → toggle "Developer Mode".');
  console.error('  3. Or: open an admin terminal and run `npm run build:win`.');
  process.exit(1);
}
