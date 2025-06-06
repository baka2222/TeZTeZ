from django.db import models
from decimal import Decimal
from django.core.validators import MinValueValidator

class Client(models.Model):
    tg_code    = models.CharField("Telegram ID", max_length=50, unique=True)
    name       = models.CharField("Имя клиента", max_length=200, blank=True, null=True)
    phone      = models.CharField("Номер телефона", max_length=30, blank=True, null=True)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or self.tg_code


class Shop(models.Model):
    owner      = models.ForeignKey(
                    Client,
                    verbose_name="Владелец",
                    on_delete=models.CASCADE,
                    related_name='shops'
                 )
    name        = models.CharField("Название магазина", max_length=200)
    address     = models.CharField("Адрес", max_length=300, blank=True, null=True)
    description = models.TextField("Описание", blank=True, null=True)
    created_at  = models.DateTimeField("Дата создания", auto_now_add=True)

    class Meta:
        verbose_name = "Мастерская"
        verbose_name_plural = "Мастерские"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    shop       = models.ForeignKey(
                    Shop,
                    verbose_name="Мастерская",
                    on_delete=models.CASCADE,
                    related_name='products'
                 )
    name       = models.CharField("Название товара", max_length=200)
    price      = models.IntegerField("Цена (KGS)", help_text="Укажите цену в целых рублях")
    description= models.TextField("Описание товара", blank=True, null=True)
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.shop.name}) — {self.price}₽"


class Service(models.Model):
    shop       = models.ForeignKey(
                    Shop,
                    verbose_name="Мастерская",
                    on_delete=models.CASCADE,
                    related_name='services'
                 )
    name       = models.CharField("Название услуги", max_length=200)
    price      = models.IntegerField("Стоимость (KGS)", help_text="Укажите стоимость в целых рублях")
    description= models.TextField("Описание услуги", blank=True, null=True)
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True)

    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.shop.name}) — {self.price}₽"


class Order(models.Model):
    shop        = models.ForeignKey(
                     Shop,
                     verbose_name="Мастерская",
                     on_delete=models.CASCADE,
                     related_name='orders'
                  )
    client      = models.ForeignKey(
                     Client,
                     verbose_name="Клиент",
                     on_delete=models.CASCADE,
                     related_name='orders'
                  )
    total_price = models.IntegerField("Итоговая сумма (KGS)", default=0)
    created_at  = models.DateTimeField("Дата заказа", auto_now_add=True)

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Заказ #{self.id} — {self.total_price}KGS"

    def recalc_total(self):
        total = 0
        for item in self.items.all():
            if item.product:
                total += item.product.price * item.quantity
            elif item.service:
                total += item.service.price * item.quantity
        self.total_price = total
        self.save()


class OrderItem(models.Model):
    order    = models.ForeignKey(
                  Order,
                  verbose_name="Заказ",
                  on_delete=models.CASCADE,
                  related_name='items'
               )
    product  = models.ForeignKey(
                  Product,
                  verbose_name="Товар",
                  on_delete=models.CASCADE,
                  null=True, blank=True
               )
    service  = models.ForeignKey(
                  Service,
                  verbose_name="Услуга",
                  on_delete=models.CASCADE,
                  null=True, blank=True
               )
    quantity = models.PositiveIntegerField("Количество", default=1)

    class Meta:
        unique_together   = ('order', 'product')
        verbose_name      = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"
        ordering          = ["order"]

    def __str__(self):
        if self.product:
            return f"{self.product.name} ×{self.quantity}"
        elif self.service:
            return f"{self.service.name} ×{self.quantity}"
        return "Пустая позиция"
