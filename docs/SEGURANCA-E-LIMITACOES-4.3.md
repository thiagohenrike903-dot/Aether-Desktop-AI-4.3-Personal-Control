# Segurança e limitações da versão 4.3

## Limites importantes

- Plugins continuam sendo código Python confiável no mesmo processo. A
  suspensão bloqueia novas execuções e descarrega handlers conhecidos, mas não
  consegue encerrar à força uma thread de plugin já em execução.
- A automação Chromium permanece bloqueada. Um navegador persistente só deve
  voltar com proxy de saída isolado, IP pinado e auditoria por requisição.
- A verificação de atualização aceita somente manifesto Ed25519 e artefato com
  SHA-256 correspondente, mas não baixa nem instala versões automaticamente.
- A cadeia de auditoria detecta divergências internas e alterações acidentais.
  Ela não é uma assinatura externa: alguém com controle total do banco também
  poderia recalcular ou apagar a cadeia. Uma âncora assinada externa continua
  recomendada para ambientes regulados.
- O verificador de resposta usa correspondência conservadora de evidências. O
  resultado ajuda a revisar, mas não substitui validação humana ou uma auditoria
  especializada.
- Avaliações pessoais usam critérios locais e saídas fornecidas. Elas não
  executam silenciosamente todos os modelos nem são uma prova absoluta de
  qualidade.
- O tempo até o primeiro token só aparece quando foi medido em streaming
  nativo. Respostas bufferizadas mostram “não medido”, nunca zero artificial.
- O índice semântico só é habilitado quando um modelo local já está configurado.
  O Aether não baixa um modelo em segundo plano.
- OCR exige Tesseract. A primeira preparação do aplicativo ainda exige Python
  3.10+ e internet ou cache local de pacotes.
- O layout móvel é responsivo, não um APK, PWA ou aplicativo para iPhone.

## Credenciais

- O renderer nunca recebe chaves, tokens OAuth ou o token interno do núcleo.
- O Electron injeta apenas concessões efetivas do cofre para o processo Python.
- Concessões de sessão somem ao fechar o aplicativo; concessões temporárias
  expiram; bloqueios impedem fallback para `.env` e arquivos legados no modo
  desktop protegido.
- Segredos são removidos do ambiente antes de iniciar Git, testes, plugins ou
  outros subprocessos.
- O backup de usuário não inclui credenciais, certificados ou arquivos `.env`.
- Snapshots de recuperação do próprio aplicativo podem incluir o arquivo
  criptografado do cofre para restaurar o estado local; seu conteúdo continua
  protegido pelo mecanismo do sistema operacional.

## Aprovação e projetos

- O renderer não pode enviar cabeçalhos HTTP arbitrários ao núcleo.
- A ponte aceita apenas um sinal booleano de confirmação e um identificador de
  projeto limitado; o processo principal os converte em cabeçalhos fixos.
- Uma aprovação antiga não supera uma política posteriormente alterada para
  Bloquear.
- Somente leitura bloqueia mudanças conhecidas e falha fechado para tipos
  desconhecidos.
- Alterar a própria política de segurança sempre exige confirmação explícita,
  inclusive para que o usuário consiga sair de Somente leitura sem criar uma
  rota de bypass silencioso.

