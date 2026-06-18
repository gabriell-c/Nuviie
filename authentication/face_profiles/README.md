# Perfis faciais (portáteis)

Cada arquivo `<email>.json` guarda o **embedding facial** (vetor 512-d) de um
usuário — **não** a foto. Eles existem para que o cadastro de reconhecimento
facial sobreviva a:

- troca de computador;
- `git clone` em outra máquina;
- recriação do banco de dados.

## Como funciona

- Ao concluir o cadastro facial (ou ativar no perfil), o arquivo é gerado/atualizado automaticamente.
- Ao abrir a tela de login facial e no boot do servidor, os arquivos são restaurados para o banco (casando pelo **e-mail** do usuário).

## Comandos úteis

```bash
python manage.py sync_faces             # restaura arquivos -> banco (não sobrescreve)
python manage.py sync_faces --overwrite # restaura e sobrescreve
python manage.py sync_faces --export    # exporta banco -> arquivos
```

> Estes arquivos são versionados de propósito. Se preferir não commitar dados
> biométricos, adicione `authentication/face_profiles/*.json` ao `.gitignore`
> e use outro mecanismo de sincronização (ex.: drive compartilhado).
