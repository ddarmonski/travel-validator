from rest_framework import serializers

class ExpenseSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    category = serializers.CharField()
    description = serializers.CharField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    date = serializers.DateTimeField()

class DocumentSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    file_name = serializers.CharField()
    file_size = serializers.IntegerField()
    file_url = serializers.URLField()
    uploaded_at = serializers.DateTimeField(read_only=True)

class RequestHistorySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    type = serializers.CharField()
    title = serializers.CharField()
    user = serializers.CharField()
    comments = serializers.CharField(allow_null=True)
    date = serializers.DateTimeField(read_only=True)

class TravelRequestSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    requester = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    department = serializers.CharField()
    position = serializers.CharField()
    documents = DocumentSerializer(many=True, read_only=True)
    expenses = ExpenseSerializer(many=True)
    history = RequestHistorySerializer(many=True, read_only=True)

    def create(self, validated_data):
        expenses_data = validated_data.pop('expenses', [])
        request = TravelRequest(**validated_data)
        request.expenses = [Expense(**expense) for expense in expenses_data]
        return request

    def update(self, instance, validated_data):
        expenses_data = validated_data.pop('expenses', [])
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.expenses = [Expense(**expense) for expense in expenses_data]
        return instance