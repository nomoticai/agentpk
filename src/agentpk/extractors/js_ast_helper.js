// js_ast_helper.js
// Usage: node js_ast_helper.js <source_file_path> [--typescript]
// Outputs: JSON StaticAnalysisFindings record to stdout
// Dependencies: acorn (optional, installed via: npm install -g acorn)

const fs = require('fs');
const path = require('path');
const filePath = process.argv[2];
const isTypeScript = process.argv.includes('--typescript');

if (!filePath) {
  process.stderr.write('Usage: node js_ast_helper.js <file> [--typescript]\n');
  process.exit(1);
}

const source = fs.readFileSync(filePath, 'utf8');
const filename = path.basename(filePath);

const findings = {
  imports: [],
  network_calls: [],
  file_reads: [],
  file_writes: [],
  subprocess_calls: [],
  env_var_accesses: [],
  tool_registrations: [],
  entry_functions: [],
  dynamic_import_detected: false,
  obfuscated_call_detected: false,
  warnings: []
};

// Try acorn parse, fall back to regex if unavailable
let ast = null;
try {
  const acorn = require('acorn');
  ast = acorn.parse(source, {
    ecmaVersion: 'latest',
    sourceType: 'module',
    locations: true,
    allowImportExportEverywhere: true,
    allowReturnOutsideFunction: true,
  });
} catch (e) {
  findings.warnings.push('acorn not available or parse error: ' + e.message + '; falling back to regex');
}

if (ast) {
  // AST-based extraction
  function walk(node, visitors) {
    if (!node || typeof node !== 'object') return;
    const visitor = visitors[node.type];
    if (visitor) visitor(node);
    for (const key of Object.keys(node)) {
      const child = node[key];
      if (Array.isArray(child)) child.forEach(c => walk(c, visitors));
      else if (child && typeof child === 'object' && child.type) walk(child, visitors);
    }
  }

  const HTTP_WRITE_METHODS = new Set(['post', 'put', 'delete', 'patch', 'del']);
  const HTTP_READ_METHODS = new Set(['get', 'head', 'options']);
  const HTTP_LIBS = new Set(['axios', 'got', 'superagent', 'node-fetch', 'fetch', 'ky']);
  const FS_WRITE = new Set(['writeFile', 'appendFile', 'createWriteStream', 'writeFileSync', 'appendFileSync']);
  const FS_READ = new Set(['readFile', 'readFileSync', 'createReadStream']);
  const SPAWN_METHODS = new Set(['exec', 'execSync', 'spawn', 'spawnSync', 'execFile', 'execFileSync']);
  const ENTRY_NAMES = new Set(['run', 'main', 'execute', 'invoke', 'handler', 'start']);

  walk(ast, {
    ImportDeclaration(node) {
      findings.imports.push({
        module: node.source.value,
        file: filename,
        line: node.loc.start.line
      });
    },
    CallExpression(node) {
      const line = node.loc && node.loc.start.line;
      const callee = node.callee;

      // require()
      if (callee.type === 'Identifier' && callee.name === 'require') {
        const arg = node.arguments[0];
        if (arg && arg.type === 'Literal') {
          findings.imports.push({ module: arg.value, file: filename, line: line });
        } else if (arg) {
          findings.dynamic_import_detected = true;
        }
      }

      // HTTP calls: axios.get(), axios.post(), etc.
      if (callee.type === 'MemberExpression') {
        const obj = callee.object && callee.object.name;
        const method = callee.property && (callee.property.name || callee.property.value);

        if (obj && HTTP_LIBS.has(obj.toLowerCase()) && method) {
          const m = method.toLowerCase();
          const isWrite = HTTP_WRITE_METHODS.has(m);
          const isRead = HTTP_READ_METHODS.has(m);
          if (isWrite || isRead) {
            const urlArg = node.arguments[0];
            if (urlArg && urlArg.type !== 'Literal' && urlArg.type !== 'TemplateLiteral') {
              findings.obfuscated_call_detected = true;
            }
            findings.network_calls.push({
              method: method.toUpperCase(),
              library: obj,
              file: filename,
              line: line
            });
          }
        }

        // http.request / https.request
        if ((obj === 'http' || obj === 'https') && method === 'request') {
          findings.network_calls.push({ method: 'UNKNOWN', library: obj, file: filename, line: line });
        }

        // fs operations
        if (obj === 'fs' && method && FS_WRITE.has(method)) {
          findings.file_writes.push({ operation: 'write', file: filename, line: line });
        }
        if (obj === 'fs' && method && FS_READ.has(method)) {
          findings.file_reads.push({ operation: 'read', file: filename, line: line });
        }

        // child_process
        if ((obj === 'child_process' || obj === 'cp') && method && SPAWN_METHODS.has(method)) {
          findings.subprocess_calls.push({ command: 'UNKNOWN', file: filename, line: line });
        }
      }

      // Direct fetch() call
      if (callee.type === 'Identifier' && callee.name === 'fetch') {
        findings.network_calls.push({ method: 'UNKNOWN', library: 'fetch', file: filename, line: line });
      }
    },

    // process.env.VAR as MemberExpression (not call)
    MemberExpression(node) {
      const line = node.loc && node.loc.start.line;
      if (node.object && node.object.type === 'MemberExpression' &&
          node.object.object && node.object.object.name === 'process' &&
          node.object.property && node.object.property.name === 'env') {
        const varName = node.property ? (node.property.name || 'UNKNOWN') : 'UNKNOWN';
        findings.env_var_accesses.push({ var_name: varName, file: filename, line: line });
      }
    },

    FunctionDeclaration(node) {
      const name = node.id && node.id.name;
      if (name && ENTRY_NAMES.has(name.toLowerCase())) {
        findings.entry_functions.push(name);
      }
    },

    // Export detection for entry functions
    ExportDefaultDeclaration(node) {
      if (node.declaration && node.declaration.type === 'FunctionDeclaration') {
        const name = node.declaration.id && node.declaration.id.name;
        if (name && !findings.entry_functions.includes(name)) {
          findings.entry_functions.push(name);
        }
      }
    },
  });

} else {
  // Regex fallback
  const lines = source.split('\n');
  lines.forEach((line, idx) => {
    const lineNum = idx + 1;
    const requireMatch = line.match(/require\(['"`]([^'"`]+)['"`]\)/);
    if (requireMatch) findings.imports.push({ module: requireMatch[1], file: filename, line: lineNum });
    const importMatch = line.match(/import\s+.*?from\s+['"]([^'"]+)['"]/);
    if (importMatch) findings.imports.push({ module: importMatch[1], file: filename, line: lineNum });
    if (/axios\.(post|put|delete|patch)\(/.test(line)) {
      const m = line.match(/axios\.(\w+)/);
      findings.network_calls.push({ method: m[1].toUpperCase(), library: 'axios', file: filename, line: lineNum });
    }
    if (/axios\.get\(/.test(line))
      findings.network_calls.push({ method: 'GET', library: 'axios', file: filename, line: lineNum });
    if (/fetch\s*\(/.test(line))
      findings.network_calls.push({ method: 'UNKNOWN', library: 'fetch', file: filename, line: lineNum });
    if (/fs\.(writeFile|appendFile|createWriteStream|writeFileSync|appendFileSync)/.test(line))
      findings.file_writes.push({ operation: 'write', file: filename, line: lineNum });
    if (/fs\.(readFile|readFileSync|createReadStream)/.test(line))
      findings.file_reads.push({ operation: 'read', file: filename, line: lineNum });
    if (/process\.env\.(\w+)/.test(line)) {
      const m = line.match(/process\.env\.(\w+)/);
      findings.env_var_accesses.push({ var_name: m[1], file: filename, line: lineNum });
    }
    if (/child_process\.(exec|spawn|execSync|spawnSync|execFile)/.test(line))
      findings.subprocess_calls.push({ command: 'UNKNOWN', file: filename, line: lineNum });
  });
}

process.stdout.write(JSON.stringify(findings));
