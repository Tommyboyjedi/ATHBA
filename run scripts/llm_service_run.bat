@echo off
setlocal

start "llm_server" /D "C:\source\python\commercial_agentic_ai" cmd /K ^
  "poetry run uvicorn llm_service.llm_server:app --host 127.0.0.1 --port 8011 --reload"

endlocal