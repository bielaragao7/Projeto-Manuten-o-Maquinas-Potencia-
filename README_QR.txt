MANUTENÇÃO MÁQUINAS v3 (com QR por máquina + PIN)

1) Rodar no PC/servidor da rede (Wi‑Fi da empresa):
   - IMPORTANTE: o QR precisa apontar para o IP desse PC na rede.

2) Criar e ativar venv:
   py -m venv venv
   venv\Scripts\activate

3) Instalar dependências:
   pip install -r requirements.txt

4) Definir BASE_URL (IP do PC na rede) e PIN (opcional):
   set BASE_URL=http://192.168.1.10:5001
   set QR_PIN=1234

   (Troque o IP para o IP real do PC que está rodando o sistema)

5) Rodar:
   py app.py

6) Login no painel:
   http://IP_DO_PC:5001/login

7) Página dos QR Codes (admin):
   http://IP_DO_PC:5001/qrcodes

8) Formulário via QR (exemplo):
   http://IP_DO_PC:5001/qr/M001

Obs:
- O formulário /qr/<patrimonio> NÃO pede login, só o PIN.
- Ao enviar, ele cria uma manutenção com status "Aberto" no sistema.
