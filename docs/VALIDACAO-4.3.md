# Validação do Aether 4.3

Data do freeze: 24 de julho de 2026.

## Resultado integrado

O comando `npm run validate` terminou com código zero e executou, na mesma
rodada:

- sincronização de `renderer/` para `dist/`;
- validação de sintaxe dos arquivos JavaScript do release;
- **61 testes Node/Electron aprovados**, sem falhas, pulos ou cancelamentos;
- `compileall` do núcleo e dos testes Python;
- **171 testes Python e 10 subtestes aprovados**;
- auditoria estrutural do release 4.3 aprovada.

A rodada foi executada em Linux x86_64 com Node.js 24.14.0, npm 11.9.0 e
Python 3.12.13.

## Contratos cobertos

### Desktop e ponte

- renderer isolado, com sandbox e sem acesso direto ao Node.js;
- allowlist por método e rota para a ponte com o núcleo;
- confirmação convertida apenas em um cabeçalho fixo;
- escopo de projeto limitado e propagado por um cabeçalho fixo;
- cancelamento correlacionado e parsing SSE fragmentado, incluindo UTF-8;
- captura de tela protegida por concessão curta, explícita e de uso único;
- arquivos selecionados acessíveis somente pela ponte dedicada;
- cobertura de todas as rotas FastAPI declaradas pela allowlist ou por IPC
  dedicado.

### Credenciais

- cofre v2, migração do formato legado e falha fechada para versões futuras;
- concessões permanentes, de sessão, temporárias e bloqueadas;
- expiração, revogação e remoção em cascata de concessões;
- recusa de armazenamento não criptografado e de links simbólicos;
- chaves OAuth restritas às integrações correspondentes;
- remoção dos segredos gerenciados do ambiente herdado;
- valores do cofre nunca retornados ao renderer.

### Atualização e recuperação

- manifesto Ed25519 obrigatório, canal estável/beta e verificação de SHA-256,
  tamanho, plataforma e arquitetura do artefato;
- recusa de chave privada, assinatura incorreta, canal divergente e artefato
  alcançado por link simbólico;
- ausência deliberada de IPC para instalar uma atualização;
- snapshots com manifesto e hashes, rejeição de arquivos extras, especiais ou
  alterados;
- reversão testada inclusive quando uma falha ocorre depois da substituição do
  primeiro diretório gerenciado.

### Release e interface

- versões coerentes entre npm, lockfile e núcleo Python;
- dependências de Electron e electron-builder fixadas exatamente no lockfile;
- fuses de produção, assinatura de atualização no Windows e filtros de
  empacotamento verificados;
- ícone, wordmark, splash, bandeja e imagens do instalador validados em seus
  formatos e dimensões;
- `renderer/` e `dist/` idênticos após o build;
- CSP, IDs duplicados, referências de IDs, `aria-controls`, tamanho mínimo de
  texto e combinações de contraste declaradas auditados estaticamente;
- identidade visual validada sem cores RGB/hex fora da escala de cinza;
- presença dos contratos visuais e funcionais 4.1–4.3 verificada no renderer.

## Validação visual em Chromium

Depois do freeze funcional, o renderer 4.3 foi aberto em um Chromium headless
temporário, externo ao pacote. Foram renderizados seis estados reais:

- painel pessoal em 1920×1080;
- modo foco com timeline e comparação em 1920×1200;
- Model Lab em 1920×1200;
- confiança e auditoria em 1920×1120;
- saúde e recuperação em 1920×1080;
- layout responsivo em 430×932.

Todos os seis estados passaram sem estouro horizontal. O axe-core foi executado
no Chromium em cada estado e não encontrou violações de impacto sério ou
crítico. As capturas foram normalizadas para escala de cinza para remover
franjas cromáticas de antialiasing subpixel; nenhum conteúdo ou componente foi
alterado.

## Trust root de atualização

Uma chave de produção não acompanha o código-fonte. Por isso, neste freeze, o
atualizador fica explicitamente indisponível e não instala nada. O release
estrutural aceita esse estado e o registra como nota.

O build de produção deve usar `npm run build:win:trusted` com
`AETHER_UPDATE_PUBLIC_KEY_FILE` apontando para uma **chave pública Ed25519**.
O preparador rejeita material privado ou de outro algoritmo. A chave privada
de assinatura nunca deve entrar no projeto ou no pacote.

O preparador também foi executado sem a variável de confiança: encerrou com
código 1 e não criou `build/update-public-key.pem`, como esperado.

## Limites desta validação

- O projeto não possui `node_modules`, executável do Electron nem
  electron-builder. Portanto, não foi gerado ou aberto um executável
  empacotado e não foi criado um instalador.
- A validação Chromium cobre seis estados representativos do renderer com
  fixtures locais. Ela não substitui uma rodada manual em cada sistema
  operacional nem afirma ter executado todas as combinações possíveis.
- A restauração é transacional dentro de cada raiz gerenciada e desfaz raízes
  já trocadas quando uma etapa posterior falha. Ela não é uma transação atômica
  única oferecida pelo sistema de arquivos entre múltiplas raízes.
- Criação, verificação e restauração de snapshots percorrem arquivos de forma
  síncrona no processo principal; estados locais muito grandes podem pausar a
  interface durante a operação.
- O aplicativo ainda requer Python 3.10+; a primeira preparação depende de
  internet ou cache local. OCR requer Tesseract, plugins continuam como código
  confiável no processo Python, Chromium permanece bloqueado e o layout móvel
  não é APK, PWA nem aplicativo iOS.

As limitações de produto e o modelo de segurança completo estão em
[`SEGURANCA-E-LIMITACOES-4.3.md`](SEGURANCA-E-LIMITACOES-4.3.md).
