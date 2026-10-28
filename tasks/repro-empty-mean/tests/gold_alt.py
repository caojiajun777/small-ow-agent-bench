def mean(nums):
    if len(nums) == 0:
        raise ValueError("empty")
    return sum(nums) / len(nums)
