// Obfuscates the frontend scripts of the desktop build: node obfuscate.mjs <dir>
// Every .js file under <dir> (except the service worker, which the desktop build does not use) is
// rewritten in place. Names that other scripts call (the global functions and constants) are kept;
// local names and string literals are scrambled. Each file gets its own identifier prefix so the
// generated helpers of different scripts can never collide in the shared global scope.
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import JavaScriptObfuscator from "javascript-obfuscator";

const root = process.argv[2];
if (!root) throw new Error("usage: node obfuscate.mjs <dir>");

function* walk(dir) {
    for (const name of readdirSync(dir).sort()) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) yield* walk(path);
        else if (name.endsWith(".js")) yield path;
    }
}

let index = 0;
for (const file of walk(root)) {
    const rel = relative(root, file).replaceAll("\\", "/");
    if (rel === "sw.js") continue;
    const source = readFileSync(file, "utf8");
    const result = JavaScriptObfuscator.obfuscate(source, {
        compact: true,
        identifiersPrefix: `v${index++}`,
        identifierNamesGenerator: "hexadecimal",
        renameGlobals: false,
        renameProperties: false,
        stringArray: true,
        stringArrayEncoding: ["base64"],
        stringArrayThreshold: 0.75,
        stringArrayWrappersCount: 1,
        splitStrings: false,
        selfDefending: false,
        debugProtection: false,
        controlFlowFlattening: false,
        deadCodeInjection: false,
        numbersToExpressions: false,
        simplify: true,
        transformObjectKeys: false,
        unicodeEscapeSequence: false,
        target: "browser",
    });
    writeFileSync(file, result.getObfuscatedCode(), "utf8");
    console.log(`obfuscated ${rel}`);
}
