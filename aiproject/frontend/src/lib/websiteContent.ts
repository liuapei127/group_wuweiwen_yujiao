export type WebsiteCard = {id: number; title: string; content: string}
export type WebsiteSection = {id: number; title: string; anchor: string; cards: WebsiteCard[]}
export const websiteContentQueryKey = ['website-content'] as const
export const publicWebsiteContentPath = '/api/v1/website/sections'
