def mean(nums):
    if not nums:
        raise ValueError("empty")
    return sum(nums) / len(nums)
