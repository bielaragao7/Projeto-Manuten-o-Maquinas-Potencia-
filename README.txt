# Manutenção Máquinas v3 (Flask)

## 1) Rodar (mais fácil)
Dê duplo clique em **run.bat**.

Ele:
- cria o venv (se não existir)
- instala as dependências
- inicia em `http://127.0.0.1:5001`

> Se abrir o CMD e fechar rápido, use o `run.bat` (ele dá `pause` no final).

## 2) Rodar pelo CMD (manual)
Abra o CMD na pasta do projeto e rode:

```bat
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
py app.py
```

## Login (demo)
- admin / 1234 (admin)
- potencia / 2524 (factory)
