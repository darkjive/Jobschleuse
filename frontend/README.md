# Jobschleuse — Frontend

React + TypeScript + Vite + shadcn/ui gegen die JSON-API der
[Jobschleuse](../README.md) unter `/api/*`.

    npm install
    npm run dev      # Hot-Reload gegen die laufende FastAPI-API (Proxy in vite.config.ts)
    npm run build    # → dist/, wird committed — uv run jobs serve braucht kein Node
    npm test         # Vitest

Details zu Architektur und Konventionen: [`../CLAUDE.md`](../CLAUDE.md#web).
