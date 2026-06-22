'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

/**
 * Carrega um script da extensão (que se anexa em `self`) num sandbox isolado
 * e devolve o objeto exportado. Permite testar as funções puras sem Chrome/DOM.
 *
 * @param {string} relativePath caminho relativo à pasta da extensão
 * @param {string} exportName nome da global anexada em `self` (ex: 'NuviieInstagramMap')
 * @param {object} [extraGlobals] globais adicionais para o sandbox
 * @returns {object} o objeto exportado pelo script
 */
function loadSelfScript(relativePath, exportName, extraGlobals = {}) {
  const filePath = path.resolve(__dirname, '..', relativePath);
  const code = fs.readFileSync(filePath, 'utf8');

  const self = {};
  const sandbox = Object.assign(
    {
      self,
      window: self,
      globalThis: self,
      console,
      ...extraGlobals,
    },
    {},
  );

  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: relativePath });

  return self[exportName];
}

module.exports = { loadSelfScript };
