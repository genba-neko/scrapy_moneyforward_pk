"""MoneyForward Scrapy pipelines."""

from moneyforward.pipelines.dynamodb import DynamoDbPipeline
from moneyforward.pipelines.json_array import JsonArrayOutputPipeline

__all__ = ["JsonArrayOutputPipeline", "DynamoDbPipeline"]
