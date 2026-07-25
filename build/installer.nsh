; NSIS installer customisation for Aether Desktop AI.
; User configuration remains in AppData after uninstall unless deleted manually.

!macro customInstall
  DetailPrint "Aether: preparing private user data..."
  SetShellVarContext current
  CreateDirectory "$APPDATA\Aether Desktop AI"

  ; Explorer integration is per-user and grants one bounded read of the exact
  ; selected file. Directories are deliberately excluded.
  WriteRegStr HKCU "Software\Classes\*\shell\AetherAsk" "MUIVerb" "Perguntar ao Aether"
  WriteRegStr HKCU "Software\Classes\*\shell\AetherAsk" "Icon" '"$INSTDIR\${APP_EXECUTABLE_FILENAME}",0'
  WriteRegStr HKCU "Software\Classes\*\shell\AetherAsk" "MultiSelectModel" "Single"
  WriteRegStr HKCU "Software\Classes\*\shell\AetherAsk\command" "" '"$INSTDIR\${APP_EXECUTABLE_FILENAME}" --ask-file "%1"'
!macroend

!macro customUnInstall
  DeleteRegKey HKCU "Software\Classes\*\shell\AetherAsk"
  ; Cleanup for older development builds that registered directories.
  DeleteRegKey HKCU "Software\Classes\Directory\shell\AetherAsk"

  ; Clear only disposable cache; preserve .env, workspace state and backups.
  RMDir /r "$APPDATA\Aether Desktop AI\Cache"
!macroend
