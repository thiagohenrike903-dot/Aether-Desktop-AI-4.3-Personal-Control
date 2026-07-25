# Validação do Aether 4.2

Data do freeze: 24 de julho de 2026.

## Resultado

- 135 testes Python aprovados, sem falhas ou erros.
- 25 testes Node/Electron aprovados.
- `compileall` do núcleo e dos testes aprovado.
- Sintaxe de todos os arquivos JavaScript do release aprovada.
- Validação estrutural do release 4.2 aprovada.
- As 11 áreas do produto, o inspetor de contexto e a visualização móvel foram
  renderizados no Chromium real.
- Zero violações detectadas pelo axe nas 13 visualizações auditadas.
- Zero estouro horizontal em 1920×1080 e 430×932.
- Renderer e `dist` sincronizados pelo build.
- Ícone, wordmark, splash, bandeja, imagens NSIS e BMP portátil validados como
  assets monocromáticos nos formatos e dimensões esperados.

## Contratos novos cobertos

- Modo global `normal`, `confirm_all` e `read_only`.
- Bloqueio fail-closed de ações desconhecidas nos modos restritivos.
- Aplicação do limite global em chat, rotas diretas, aprovação, repetição,
  desfazer e automações.
- Contexto real por conversa, pai e ramificação, sem misturar projetos.
- Persistência do `request_id` real no streaming.
- Inspetor de contexto sem efeitos colaterais e sem valores privados completos.
- Sanitização da ação antes do limite do provedor de modelo.
- Exportação redigida da auditoria com eventos, filtros e checksum informativo.
- Restauração segura de janela, estado de bandeja e progresso nativo.

## Regressões visuais cobertas

- Paleta restrita a preto, branco e cinza.
- Logo original aplicada em interface, avatar, splash e ícone.
- Contraste mínimo de 4,5:1 nas combinações verificadas.
- Nenhum controle focável dentro de regiões ocultas.
- Ordem de títulos correta nas páginas de Projetos e Modelos.
- Árvore do Workspace com semântica de lista válida.
- Projeto ativo visível sem quebrar a navegação móvel.

## Limitações verificadas

- Python 3.10+ ainda precisa existir no sistema. O pacote cria uma `venv` e
  instala o núcleo na primeira abertura, mas não incorpora um runtime offline.
- Plugins continuam no processo do núcleo e devem ser tratados como código
  confiável.
- Automação Chromium permanece bloqueada até existir um proxy de saída com
  DNS/IP pinado.
- OCR requer o pacote opcional e o executável Tesseract.
- O checksum da auditoria detecta diferenças no conteúdo exportado, mas não é
  uma prova contra alguém com acesso de escrita ao banco e ao aplicativo.
