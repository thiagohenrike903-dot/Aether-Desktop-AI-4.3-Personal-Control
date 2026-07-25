# Validação do Aether 4.1

Data do freeze: 24 de julho de 2026.

## Resultado

- 123 testes Python aprovados e 10 subtestes aprovados.
- 21 testes Node/Electron aprovados.
- `compileall` do núcleo e dos testes aprovado.
- Sintaxe de todos os arquivos JavaScript do release aprovada.
- 11 páginas da interface inicializadas no smoke DOM.
- Nenhuma violação séria ou crítica no axe executado sobre o DOM.
- Renderer e `dist` idênticos após o build.
- Contratos de streaming, operações, permissões, memória, projetos, pesquisa,
  modelos, automações, captura de região e cofre verificados.
- Tamanho mínimo explícito de texto: 12 px.
- Tokens principais dos temas claro e escuro verificados com contraste mínimo
  de 4,5:1 nas combinações de texto usadas.
- Varredura ampla de assinaturas de credenciais aprovada.

## Regressões de segurança cobertas

- DNS rebinding entre validação e conexão.
- DNS misto público/privado e IPv4 privado mapeado em IPv6.
- Preservação de `Host` e SNI ao conectar ao IP público pinado.
- Proxies de ambiente ignorados na abertura de fontes públicas.
- Redação de credenciais em URL, query, fragmento OAuth, headers, flags CLI,
  erros, operações e logs divididos entre chunks.
- Arquivos sensíveis ocultos da árvore, leitura, busca e importação em pasta.
- Grants temporários de leitura somente para arquivos escolhidos.
- Limites do stream SSE, correlação de request e cancelamento.
- Sandbox, CSP, `contextIsolation` e ponte IPC estreita.
- Recuperação de operações incompletas após reinício sem reexecutar payloads.

## Limitações verificadas

- Python 3.10+ ainda precisa existir no sistema. O pacote cria uma `venv` e
  instala o núcleo na primeira abertura, mas não incorpora um runtime offline.
- Plugins continuam no processo do núcleo e devem ser tratados como código
  confiável.
- Automação Chromium permanece bloqueada até existir um proxy de saída com
  DNS/IP pinado.
- OCR requer o pacote opcional e o executável Tesseract.
- Workers síncronos sem cancelamento cooperativo podem terminar internamente
  depois de a interface e o transporte já terem sido interrompidos.
