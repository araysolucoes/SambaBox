# Política de segurança

O SambaBox é experimental e **não deve ser empregado em ambiente de produção** no estado atual.

## Divulgação responsável

**Não publique** senhas, arquivos `cloud-init-seed.iso`, chaves privadas SSH, discos virtuais, dumps ou endereços internos em issues públicas.

Para relatar vulnerabilidades, prefira o recurso **Report a vulnerability / Private vulnerability reporting** da aba **Security** no GitHub, se estiver habilitado no repositório. Caso não esteja, solicite aos mantenedores um canal privado antes de enviar detalhes sensíveis. Para contato com os mantenedores: aray.solucoes@gmail.com.

## Versões suportadas

Não há versão estável suportada. O código na branch `main` é de laboratório; patches de segurança são aplicados conforme disponibilidade.

## Riscos conhecidos

- Senha administrativa compartilhada entre contas e Samba;
- credenciais transitórias armazenadas em ISO de cloud-init e impressas no console;
- host key SSH aceita automaticamente no primeiro contato;
- descoberta IPv4 restrita à LAN /24;
- instalações de dependências sem pinagem;
- falta de testes automatizados de ACLs, leitura/escrita SMB e segurança de exclusão;
- possibilidade de o `cloud-init` terminar com erro enquanto a configuração é recuperada via SSH.

Antes de liberar versão estável, esses riscos devem ser tratados ou documentados com mitigações específicas.
