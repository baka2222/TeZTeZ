from django.db import models
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.utils.functional import cached_property
from math import radians, sin, cos, sqrt, atan2

class Client(models.Model):
    tg_code = models.CharField("Telegram ID", max_length=50, unique=True)
    name = models.CharField("Имя клиента", max_length=200, blank=True, null=True)
    phone = models.CharField("Номер телефона", max_length=30, blank=True, null=True)
    username = models.CharField("Юзернейм", max_length=150, blank=True, null=True)
    is_banned = models.BooleanField("Забанен", default=False)
    next_ability = models.DateTimeField(
        "Когда можно будет снова публиковать", null=True, blank=True
    )
    next_ability_beauty = models.DateTimeField(
        "Когда можно будет снова публиковать BEAUTY", null=True, blank=True
    )
    next_ability_automoto = models.DateTimeField(
        "Когда можно будет снова публиковать AUTO/MOTO", null=True, blank=True
    )
    next_ability_housing = models.DateTimeField(
        "Когда можно будет снова публиковать HOUSING", null=True, blank=True
    )
    next_ability_techno = models.DateTimeField(
        "Когда можно будет снова публиковать TECHNO", null=True, blank=True
    )
    next_ability_job = models.DateTimeField(
        "Когда можно будет снова публиковать JOB", null=True, blank=True
    )

    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or self.tg_code

class Category(models.Model):
    name = models.CharField("Название категории", max_length=100, unique=True)
    description = models.TextField("Описание категории", blank=True, null=True)

    class Meta:
        verbose_name = "Категория магазина"
        verbose_name_plural = "Категории магазинов"
        ordering = ["name"]

    def __str__(self):
        return self.name

class Shop(models.Model):
    owner = models.ForeignKey(
        Client,
        verbose_name="Владелец",
        on_delete=models.CASCADE,
        related_name='shops'
    )
    category = models.ForeignKey(
        Category,
        verbose_name="Категория магазина",
        on_delete=models.SET_NULL,
        null=True,
        related_name='shops'
    )
    point_a_lat = models.FloatField("Широта точки А")
    point_a_lng = models.FloatField("Долгота точки А")
    name = models.CharField("Название магазина", max_length=200)
    address = models.CharField("Адрес", max_length=300, blank=True, null=True)
    description = models.TextField("Описание", blank=True, null=True)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)

    class Meta:
        verbose_name = "Магазин"
        verbose_name_plural = "Магазины"
        ordering = ["name"]

    def __str__(self):
        return self.name

class Product(models.Model):
    shop = models.ForeignKey(
        Shop,
        verbose_name="Магазин",
        on_delete=models.CASCADE,
        related_name='products'
    )
    name = models.CharField("Название товара", max_length=200)
    price = models.IntegerField(
        "Цена (KGS)",
        validators=[MinValueValidator(0)]
    )
    description = models.TextField("Описание товара", blank=True, null=True)
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.shop.name}) — {self.price}KGS"

class Service(models.Model):
    shop = models.ForeignKey(
        Shop,
        verbose_name="Магазин",
        on_delete=models.CASCADE,
        related_name='services'
    )
    name = models.CharField("Название услуги", max_length=200)
    price = models.IntegerField(
        "Стоимость (KGS)",
        validators=[MinValueValidator(0)]
    )
    description = models.TextField("Описание услуги", blank=True, null=True)
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True)

    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.shop.name}) — {self.price}KGS"

class Order(models.Model):
    shop = models.ForeignKey(
        Shop,
        verbose_name="Магазин",
        on_delete=models.CASCADE,
        related_name='orders'
    )
    client = models.ForeignKey(
        Client,
        verbose_name="Клиент",
        on_delete=models.CASCADE,
        related_name='orders'
    )
    total_price = models.IntegerField("Итоговая сумма (KGS)", default=0)
    created_at = models.DateTimeField("Дата заказа", auto_now_add=True)

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Заказ #{self.id} — {self.total_price}KGS"

class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        verbose_name="Заказ",
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        verbose_name="Товар",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    service = models.ForeignKey(
        Service,
        verbose_name="Услуга",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    quantity = models.PositiveIntegerField("Количество", default=1)

    class Meta:
        unique_together = ('order', 'product')
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"
        ordering = ["order"]

    def __str__(self):
        if self.product:
            return f"{self.product.name} ×{self.quantity}"
        if self.service:
            return f"{self.service.name} ×{self.quantity}"
        return "Пустая позиция"

# --------------- Новые модели для курьерской доставки ---------------

class PricingRule(models.Model):
    """Правило ценообразования по дистанции"""
    name = models.CharField("Название правила", max_length=100, unique=True)
    min_distance = models.FloatField("Минимальная дистанция (км)", default=0,
                                     help_text="Включительно")
    max_distance = models.FloatField("Максимальная дистанция (км)", default=0,
                                     help_text="Исключительно; 0 = без лимита")
    base_price = models.DecimalField("Базовая цена (сом)", max_digits=8, decimal_places=2, default=0)
    per_km_price = models.DecimalField("Цена за км (сом)", max_digits=8, decimal_places=2, default=0)
    multiplier = models.DecimalField("Множитель", max_digits=4, decimal_places=2, default=1,
                                     help_text="Дополнительная наценка")

    class Meta:
        ordering = ['min_distance']
        verbose_name = 'Правило ценообразования'
        verbose_name_plural = 'Правила ценообразования'

    def applies(self, distance_km: float) -> bool:
        upper = self.max_distance if self.max_distance > 0 else float('inf')
        return self.min_distance <= distance_km < upper

class TimeSurcharge(models.Model):
    """Наценка по времени суток"""
    name = models.CharField("Название наценки", max_length=100, unique=True)
    start_time = models.TimeField("Начало периода")
    end_time = models.TimeField("Конец периода")
    multiplier = models.DecimalField("Множитель", max_digits=4, decimal_places=2, default=1)

    class Meta:
        verbose_name = 'Наценка по времени'
        verbose_name_plural = 'Наценки по времени'

    def applies(self, check_time) -> bool:
        if self.start_time < self.end_time:
            return self.start_time <= check_time < self.end_time
        return check_time >= self.start_time or check_time < self.end_time

class CourierOrder(models.Model):
    """Модель чистой доставки (не привязана к магазину)"""
    client = models.ForeignKey(
        Client, verbose_name="Клиент", on_delete=models.CASCADE,
        related_name='delivery_orders'
    )
    courier = models.ForeignKey(
        Client, verbose_name="Курьер", on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_deliveries'
    )
    point_a_lat = models.FloatField("Широта точки А")
    point_a_lng = models.FloatField("Долгота точки А")
    point_b_lat = models.FloatField("Широта точки Б")
    point_b_lng = models.FloatField("Долгота точки Б")
    STATUS_CHOICES = [
        ('new', 'Новый'),
        ('assigned', 'Назначен'),
        ('to_a', 'В пути до точки А'),
        ('to_b', 'В пути до точки Б'),
        ('arrived', 'Приехал'),
        ('completed', 'Завершён'),
    ]
    status = models.CharField(
        "Статус заказа",
        max_length=20,
        choices=STATUS_CHOICES,
        default='new',
    )
    comment = models.TextField("Комментарий", blank=True)

    distance_km = models.DecimalField(
        "Расстояние (км)", max_digits=6, decimal_places=2,
        validators=[MinValueValidator(0)], null=True, blank=True
    )
    price = models.DecimalField(
        "Цена (сом)", max_digits=8, decimal_places=2,
        validators=[MinValueValidator(0)], null=True, blank=True
    )

    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)

    class Meta:
        verbose_name = "Курьерский заказ"
        verbose_name_plural = "Курьерские заказы"
        ordering = ['-created_at']

    def __str__(self):
        return f"Доставка #{self.id} от {self.client}"

    def save(self, *args, **kwargs):
        # Рассчитать расстояние и цену при сохранении
        # Формула гаверсинуса
        R = 6371.0
        lat1, lon1, lat2, lon2 = map(radians, [
            self.point_a_lat, self.point_a_lng,
            self.point_b_lat, self.point_b_lng
        ])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        dist = round(R * c, 2)
        self.distance_km = dist

        # Поиск правила
        rule = None
        for r in PricingRule.objects.all():
            if r.applies(dist):
                rule = r
                break
        if not rule and PricingRule.objects.exists():
            rule = PricingRule.objects.last()
        if rule:
            price = float(rule.base_price) + dist * float(rule.per_km_price)
            price *= float(rule.multiplier)
            # наценка по времени
            now = self.created_at.time()
            for ts in TimeSurcharge.objects.all():
                if ts.applies(now):
                    price *= float(ts.multiplier)
            self.price = round(price, 2)

        super().save(*args, **kwargs)

    def get_2gis_link(self) -> str:
        return (
            f"https://2gis.kg/routeSearch/geo/"
            f"{self.point_a_lat},{self.point_a_lng}/"
            f"{self.point_b_lat},{self.point_b_lng}"
        )
