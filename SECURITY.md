# Segurança do Aether Desktop AI

O Aether controla recursos locais sensíveis. A versão 4.3 foi organizada para
operar com privilégios mínimos, tornar as operações observáveis e pedir
confirmação antes de efeitos relevantes.

## Proteções principais

- O núcleo Python escuta apenas em `127.0.0.1` por padrão.
- O Electron cria um token aleatório a cada inicialização. Chamadas protegidas
  ao núcleo passam por uma ponte IPC isolada; o token não é exposto à página.
- A janela usa `contextIsolation`, sandbox, CSP, navegação bloqueada e
  `nodeIntegration` desativado.
- Operações destrutivas ou externas — apagar, mover, organizar de verdade,
  restaurar backup, executar plugin, enviar e-mail, alterar Git ou preencher uma
  página — passam pela Central de Controle e pela política do respectivo escopo.
- As políticas disponíveis são `ask`, `session_allow` e `block`. Uma regra de
  bloqueio prevalece mesmo quando a operação já estava aguardando aprovação.
- O modo de proteção global limita todas as políticas: `confirm_all` exige
  aprovação para qualquer ação conhecida e `read_only` bloqueia alterações. Tipos
  desconhecidos falham fechados nos dois modos restritivos.
- Projetos podem possuir um teto próprio de proteção. O renderer não envia
  cabeçalhos arbitrários: somente confirmação booleana e identificador de
  projeto limitado atravessam a ponte, e o processo principal cria os
  cabeçalhos internos.
- Alterar uma política de proteção sempre exige confirmação. Isso também
  permite sair de `read_only` sem criar uma rota silenciosa de bypass.
- O inspetor de contexto mostra somente metadados e contagens redigidas do que
  pode influenciar a próxima resposta. Valores completos não são devolvidos à
  interface e uma prévia nunca executa a ação analisada.
- A auditoria reutiliza a redação compartilhada, permite investigação por
  dimensões e mantém uma cadeia SHA-256 interna. Ela detecta divergências, mas
  não substitui uma âncora assinada fora do banco contra um invasor com controle
  total do armazenamento.
- Eventos de operações guardam resumos limitados e sanitizados; ações completas
  ficam somente na memória do processo enquanto ainda podem ser executadas.
- Erros de provedor, URLs, headers e logs do núcleo passam por redação
  compartilhada de chaves, tokens, cookies e credenciais, inclusive quando uma
  URL sensível aparece dentro de uma frase ou chega dividida entre chunks.
- O workspace impede fuga de diretório, oculta e bloqueia `.env.*`, credenciais,
  chaves, certificados e outros arquivos sensíveis, e usa hash para detectar
  conflitos antes de sobrescrever arquivos. A importação de pastas aplica a
  mesma política e informa quantos itens foram ignorados.
- Backups ignoram credenciais, dependências, builds e outros arquivos sensíveis.
- O backup completo do usuário usa uma lista fechada de componentes, valida hash
  por arquivo, pode ser criptografado e cria um snapshot anterior à restauração.
- Importação por caminho é limitada à raiz do projeto ou workspace. Arquivos
  escolhidos fora dessas raízes atravessam a ponte como conteúdo limitado.
- A abertura de fontes da Pesquisa Profissional valida o conjunto DNS completo
  em cada conexão, rejeita respostas mistas públicas/privadas, conecta ao IP
  literal validado, preserva `Host`/SNI e ignora proxies do ambiente.
  Redirecionamentos repetem o mesmo fluxo, fechando a janela de DNS
  rebinding/TOCTOU.
- A automação Chromium está desativada em modo fail-closed. Interceptação do
  Playwright não garante que o IP usado no socket seja o IP validado; ela só
  poderá ser reativada por um proxy de saída pinado e auditável.
- O aplicativo empacotado prepara uma `venv` privada no diretório de dados. A
  saída do `pip` não é gravada nem incluída em mensagens de erro, pois índices e
  proxies corporativos podem conter credenciais.

## Credenciais

Nunca coloque chaves reais em `.env.example`, commits, mensagens, automações ou
skills. Prefira o cofre do sistema oferecido pela tela de Conexões. Ele só é
habilitado quando o Electron informa que `safeStorage` usa criptografia
adequada; o fallback Linux `basic_text` é recusado.

Somente no uso independente do núcleo Python para desenvolvimento, copie
`.env.example` para `.env` e mantenha esse arquivo no computador. O Electron
protegido torna o cofre autoritativo e ignora segredos de `.env`; uma concessão
negada ou revogada nunca pode voltar por esse caminho.

Se uma chave tiver sido compartilhada em um ZIP, repositório ou conversa,
considere-a exposta: revogue-a no provedor e gere outra.

## Plugins

Plugins são código Python e ainda podem acessar os mesmos dados do processo
Aether. Instale e execute apenas arquivos cuja origem e conteúdo você verificou.
Confirmação reduz execução acidental, mas não transforma código desconhecido em
código seguro. Isolamento por subprocesso ou contêiner e manifesto assinado
continuam pendentes.

## Limites de confiança

Respostas de modelos podem conter erros. Revise caminhos, destinatários, diffs,
comandos e resumos de confirmação antes de aprovar.

Para uso corporativo, recomenda-se ainda assinatura de código, distribuição com
Python incorporado, atualização assinada, isolamento forte de plugins e uma
política central administrável.
