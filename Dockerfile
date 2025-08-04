# Python 3.11 image-ni ishlatamiz
FROM python:3.11

# Ishchi papkani yaratamiz
WORKDIR /app

# Kerakli fayllarni nusxalaymiz
COPY . /app/

# Python kutubxonalarini o‘rnatamiz
RUN pip install --no-cache-dir -r requirements.txt

# Botni ishga tushiramiz
CMD ["python", "main.py"]
