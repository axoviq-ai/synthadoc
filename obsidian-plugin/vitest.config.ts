import { defineConfig } from "vitest/config";
import { fileURLToPath } from "url";
import path from "path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
    resolve: {
        alias: {
            obsidian: path.resolve(__dirname, "__mocks__/obsidian.ts"),
        },
    },
    test: {
        environment: "node",
        exclude: ["src/**/*.integration.test.ts", "**/node_modules/**", "**/dist/**"],
        coverage: {
            provider: "v8",
            include: ["src/**/*.ts"],
            exclude: ["src/**/*.test.ts"],
            reporter: ["text", "html"],
        },
    },
});
