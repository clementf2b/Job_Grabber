import { defineConfig } from 'vite'
import fs from 'fs'
import path from 'path'

export default defineConfig({
  server: {
    port: 5173,
    open: true,
  },
  plugins: [
    {
      // Serve jobs.json directly from the project root so fetch('jobs.json')
      // works during dev. Vite's publicDir only covers the public/ folder by
      // default; this middleware fills the gap for a single file.
      name: 'serve-jobs-json',
      configureServer(server) {
        server.middlewares.use('/jobs.json', (_req, res) => {
          const file = path.resolve(process.cwd(), 'jobs.json')
          try {
            res.setHeader('Content-Type', 'application/json')
            res.end(fs.readFileSync(file, 'utf-8'))
          } catch {
            res.statusCode = 404
            res.end('[]')
          }
        })
      },
    },
  ],
})
