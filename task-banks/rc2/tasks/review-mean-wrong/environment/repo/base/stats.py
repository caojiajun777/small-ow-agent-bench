def mean(nums):
    if not nums or len(nums) > 1000 or any(type(value) is not int or abs(value) > 1_000_000 for value in nums):
        raise ValueError("invalid integer batch")
    return sum(nums)

